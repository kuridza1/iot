import { Component, Input, OnDestroy, OnInit, NgZone, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { io, Socket } from 'socket.io-client';

type WsEvt = {
  device?: string;
  type?: string;
  code?: string;
  value?: any;
  unit?: string | null;
  ts?: number;
};

interface PendulumState {
  angle: number;       // current angle in degrees
  velocity: number;    // angular velocity deg/s
  damping: number;     // damping coefficient (0–1), higher = faster decay
  running: boolean;
}

@Component({
  selector: 'app-gsg',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './gsg.html',
  styleUrl: './gsg.css',
})
export class Gsg implements OnInit, OnDestroy {
  @Input() apiBase = 'http://localhost:5000';
  @Input() device  = 'PI2';

  // ── Telemetry ──────────────────────────────────────────────────────────────
  mag     = 0;
  lastTs?: number;

  // ── UI bindings ────────────────────────────────────────────────────────────
  rotateDeg = 0;
  swingPx   = 0;

  // ── Alarm ──────────────────────────────────────────────────────────────────
  @Input() alarmThreshold  = 1.2;
  @Input() alarmCooldownMs = 5000;
  private lastAlarmAt      = 0;

  // ── Pendulum engine ────────────────────────────────────────────────────────
  private readonly MAX_IMPULSE_DEG = 28;
  private readonly MAG_SCALE       = 2.5;
  private readonly DAMPING         = 0.58;

  private pendulum: PendulumState = {
    angle:    0,
    velocity: 0,
    damping:  this.DAMPING,
    running:  false,
  };

  private rafId?: number;
  private lastFrameTime?: number;

  // throttle detectChanges during RAF (avoid 60fps full CD if not needed)
  private lastCdAt = 0;
  private readonly CD_MIN_MS = 50; // ~20 fps is enough for this UI

  // ── WebSocket ──────────────────────────────────────────────────────────────
  private sock?: Socket;

  constructor(
    private zone: NgZone,
    private cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    this.connectWs();
  }

  ngOnDestroy(): void {
    this.stopLoop();
    try { this.sock?.disconnect(); } catch {}
  }

  private connectWs(): void {
    const url = this.apiBase.replace(/\/+$/, '');

    this.sock = io(url, {
      transports: ['websocket'],
      upgrade: false,
      path: '/socket.io',
      query: { device: this.device },
    });

    this.sock.on('connect', () => {
      try { this.sock?.emit('set_device', { device: this.device }); } catch {}
    });

    // IMPORTANT: do NOT rely on NgZone for CD; explicitly refresh view
    this.sock.on('evt', (evt: WsEvt) => {
      // keep it simple: update state in JS thread, then detectChanges
      this.onEvt(evt);
    });
  }

  private onEvt(evt: WsEvt): void {
    if (!evt) return;
    if ((evt.device || '').toUpperCase() !== this.device.toUpperCase()) return;

    if (evt.code === 'GSG_MAG') {
      const raw = (evt as any).value_num ?? (evt as any).value ?? 0;
      const v = Number(raw);
      if (!Number.isFinite(v)) return;

      this.mag = v;
      this.lastTs = evt.ts;

      this.kickPendulum(v);
      this.maybeTriggerAlarmFromFrontend(v);

      // Force template refresh even in zoneless mode
      try { this.cdr.detectChanges(); } catch {}
    }
  }

  private kickPendulum(mag: number): void {
    const clamped    = Math.max(0, Math.min(this.MAG_SCALE, mag));
    const normalized = clamped / this.MAG_SCALE;

    const impulse = this.MAX_IMPULSE_DEG * Math.pow(normalized, 0.6);
    const direction = Math.random() < 0.5 ? 1 : -1;

    this.pendulum.velocity += direction * impulse * 3.5;

    const maxVel = this.MAX_IMPULSE_DEG * 5;
    this.pendulum.velocity = Math.max(-maxVel, Math.min(maxVel, this.pendulum.velocity));

    if (!this.pendulum.running) {
      this.startLoop();
    }
  }

  private startLoop(): void {
    this.pendulum.running = true;
    this.lastFrameTime    = performance.now();

    // RAF outside Angular is fine; we manually refresh view anyway
    this.zone.runOutsideAngular(() => {
      const tick = (now: number) => {
        const dt = Math.min((now - (this.lastFrameTime ?? now)) / 1000, 0.05);
        this.lastFrameTime = now;

        this.stepPendulum(dt);

        // update bound fields
        this.rotateDeg = this.pendulum.angle;
        this.swingPx   = this.pendulum.angle * 0.35;

        // Stop when motion is negligible
        if (Math.abs(this.pendulum.velocity) < 0.05 && Math.abs(this.pendulum.angle) < 0.05) {
          this.pendulum.angle    = 0;
          this.pendulum.velocity = 0;
          this.pendulum.running  = false;

          this.rotateDeg = 0;
          this.swingPx   = 0;

          try { this.cdr.detectChanges(); } catch {}
          return;
        }

        // Throttle CD so it doesn't hammer the app
        if (now - this.lastCdAt >= this.CD_MIN_MS) {
          this.lastCdAt = now;
          try { this.cdr.detectChanges(); } catch {}
        }

        this.rafId = requestAnimationFrame(tick);
      };

      this.rafId = requestAnimationFrame(tick);
    });
  }

  private stopLoop(): void {
    if (this.rafId != null) {
      cancelAnimationFrame(this.rafId);
      this.rafId = undefined;
    }
    this.pendulum.running = false;
  }

  private stepPendulum(dt: number): void {
    const p = this.pendulum;

    const springK     = 18;
    const restoring   = -springK * p.angle;

    const dampingForce = -p.damping * 8 * p.velocity;

    const accel = restoring + dampingForce;

    p.velocity += accel * dt;
    p.angle    += p.velocity * dt;

    p.angle = Math.max(-this.MAX_IMPULSE_DEG, Math.min(this.MAX_IMPULSE_DEG, p.angle));
  }

  private maybeTriggerAlarmFromFrontend(m: number): void {
    const now = Date.now();
    if (m < this.alarmThreshold) return;
    if (now - this.lastAlarmAt < this.alarmCooldownMs) return;
    this.lastAlarmAt = now;

    fetch(`${this.apiBase.replace(/\/+$/, '')}/cmd`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        device: 'PI1',
        cmd:    'ALARM_SET',
        value:  { active: true, reason: 'GSG_MOVE_FE', magnitude: m },
      }),
    }).catch(() => {});
  }

  get magLabel(): string {
    return this.mag.toFixed(2);
  }
}