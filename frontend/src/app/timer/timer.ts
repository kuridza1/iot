import { Component, Inject, OnDestroy, OnInit, PLATFORM_ID } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { TelemetryService } from '../service/telemetry.service';

@Component({
  selector: 'app-timer',
  standalone: true,
  templateUrl: './timer.html',
  styleUrl: './timer.css',
  imports: [FormsModule],
})
export class Timer implements OnInit, OnDestroy {
  device = 'PI2';

  display = '00:00';
  setSeconds = 60;
  addSeconds = 5;

  // Blink control: if idle and user pressed BTN once, stop blinking until timer leaves 00:00
  blinkSuppressed = false;

  private isBrowser: boolean;
  private sub?: Subscription;

  // Fail-safe: if no telemetry update for N ms -> force 00:00
  private lastTelemetryAt = 0;
  private watchdogTimer?: any;
  private readonly staleMs = 3000;

  constructor(
    @Inject(PLATFORM_ID) platformId: Object,
    private telemetry: TelemetryService
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  async ngOnInit(): Promise<void> {
    if (!this.isBrowser) return;

    // Always show something immediately
    this.display = '00:00';

    await this.loadInitialState();

    // Realtime ONLY through service (service must avoid duplicates)
    this.telemetry.connect('http://localhost:5000');

    this.sub = this.telemetry.getState().subscribe((snap) => {
      this.lastTelemetryAt = Date.now();

      const kText = `${this.device}:4SD`;
      const kRem = `${this.device}:4SD_REM`;

      const text = snap?.[kText]?.value;
      const rem = Number(snap?.[kRem]?.value);

      if (typeof text === 'string' && text.length) {
        this.display = text;
      } else if (Number.isFinite(rem)) {
        this.display = this.formatMMSS(rem);
      } else {
        this.display = '00:00';
      }

      // If timer left idle state, allow blinking next time it returns to 00:00
      if (this.display !== '00:00') {
        this.blinkSuppressed = false;
      }
    });

    // Watchdog: if telemetry “utihne”, UI falls back to 00:00
    this.watchdogTimer = setInterval(() => {
      if (!this.lastTelemetryAt) return;
      if (Date.now() - this.lastTelemetryAt > this.staleMs) {
        this.display = '00:00';
        // keep suppressed as-is (your choice); I’d reset so idle blinks again
        this.blinkSuppressed = false;
      }
    }, 500);
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
    if (this.watchdogTimer) clearInterval(this.watchdogTimer);
    this.watchdogTimer = undefined;
  }

  private async loadInitialState(): Promise<void> {
    try {
      const res = await fetch(
        `http://localhost:5000/telemetry/state?device=${this.device}&codes=4SD,4SD_REM,BTN`
      );
      if (!res.ok) return;

      const data = await res.json();
      const st = data?.state ?? {};

      const text = st['4SD']?.value;
      if (typeof text === 'string' && text.length) {
        this.display = text;
        return;
      }

      const rem = Number(st['4SD_REM']?.value);
      if (Number.isFinite(rem)) {
        this.display = this.formatMMSS(rem);
      }
    } catch {
      // ignore
    }
  }

  private formatMMSS(totalSeconds: number): string {
    const sec = Math.max(0, Math.floor(totalSeconds));
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }

  private async post(path: string, body: any): Promise<void> {
    const res = await fetch(`http://localhost:5000${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const txt = await res.text().catch(() => '');
      throw new Error(`HTTP ${res.status}: ${txt}`);
    }
  }

  async applySetTime(): Promise<void> {
    await this.post('/pi2/timer/set', { device: this.device, seconds: this.setSeconds });
  }

  async applyAddSeconds(): Promise<void> {
    await this.post('/pi2/timer/add-seconds-config', {
      device: this.device,
      addSeconds: this.addSeconds,
    });
  }

  async start(): Promise<void> {
    await this.post('/pi2/timer/run', { device: this.device, running: true });
  }

  async stop(): Promise<void> {
    await this.post('/pi2/timer/run', { device: this.device, running: false });
  }

  async reset(): Promise<void> {
    await this.post('/pi2/timer/reset', { device: this.device });
    // After reset you likely want blinking again
    this.blinkSuppressed = false;
    this.display = '00:00';
  }

  async pressBtn(): Promise<void> {
    // UI rule:
    // If idle (00:00 blinking), pressing BTN stops blinking (keeps 00:00 steady).
    if (this.display === '00:00') {
      this.blinkSuppressed = true;
    }

    // Always forward BTN to server; server decides (+N) when running.
    await this.post('/pi2/btn/press', { device: this.device });
  }
}