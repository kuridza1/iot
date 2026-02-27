import {
  Component,
  Inject,
  OnDestroy,
  OnInit,
  OnChanges,
  SimpleChanges,
  Input,
  PLATFORM_ID,
  ChangeDetectorRef,
} from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { WsService } from '../../ws.service';

@Component({
  selector: 'app-timer',
  standalone: true,
  templateUrl: './timer.html',
  styleUrl: './timer.css',
  imports: [FormsModule],
})
export class Timer implements OnInit, OnChanges, OnDestroy {
  @Input({ required: true }) apiBase = 'http://localhost:5000';
  @Input({ required: true }) device = 'PI2';

  display = '00:00';
  setSeconds = 60;
  addSeconds = 5;

  blinkSuppressed = false;
  busy = false;

  private isBrowser: boolean;
  private sub?: Subscription;

  private lastEvtAt = 0;
  private watchdogTimer?: any;
  private readonly staleMs = 3000;

  constructor(
    @Inject(PLATFORM_ID) platformId: Object,
    private ws: WsService,
    private cdr: ChangeDetectorRef,
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  async ngOnInit(): Promise<void> {
    if (!this.isBrowser) return;

    this.display = '00:00';
    this.cdr.markForCheck();

    this.ws.ensureConnected(this.apiBase, this.device);
    this.ws.setDevice(this.device);

    await this.loadInitialState();

    this.sub = this.ws.evt.subscribe((e: any) => {
      if (!e) return;
      this.lastEvtAt = Date.now();
      if (this.handleEvt(e)) {
        if (this.display !== '00:00') this.blinkSuppressed = false;
        this.cdr.markForCheck();
      }
    });

    this.watchdogTimer = setInterval(() => {
      if (!this.lastEvtAt) return;
      if (Date.now() - this.lastEvtAt > this.staleMs) {
        this.display = '00:00';
        this.blinkSuppressed = false;
        this.cdr.markForCheck();
      }
    }, 500);
  }

  ngOnChanges(ch: SimpleChanges): void {
    if (!this.isBrowser) return;

    if (ch['apiBase'] && !ch['apiBase'].firstChange) {
      this.ws.ensureConnected(this.apiBase, this.device);
      this.ws.setDevice(this.device);
      void this.loadInitialState();
    }

    if (ch['device'] && !ch['device'].firstChange) {
      this.ws.setDevice(this.device);
      this.display = '00:00';
      this.blinkSuppressed = false;
      this.lastEvtAt = 0;
      this.cdr.markForCheck();
      void this.loadInitialState();
    }
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
    if (this.watchdogTimer) clearInterval(this.watchdogTimer);
    this.watchdogTimer = undefined;
  }

  // Map WS "evt" payload -> UI
  // Expected from MQTT payload (as forwarded by server): { device, code, value, ts }
  // Returns true if the event affected the display.
  private handleEvt(e: any): boolean {
    const code = String(e?.code ?? '').trim();
    const value = e?.value;

    if (!code) return false;

    if (code === '4SD') {
      if (typeof value === 'string' && value.length) {
        this.display = value;
        return true;
      }
      // if sometimes numeric seconds are sent on 4SD
      const asNum = Number(value);
      if (Number.isFinite(asNum)) {
        this.display = this.formatMMSS(asNum);
        return true;
      }
      return false;
    }

    if (code === '4SD_REM') {
      const rem = Number(value);
      this.display = Number.isFinite(rem) ? this.formatMMSS(rem) : '00:00';
      return true;
    }

    return false;
  }

  // You have /telemetry/latest; use it for initial UI.
  private async loadInitialState(): Promise<void> {
    try {
      const base = this.apiBase.replace(/\/+$/, '');
      const [t, r] = await Promise.all([
        fetch(`${base}/telemetry/latest?device=${encodeURIComponent(this.device)}&code=4SD`).then((x) =>
          x.ok ? x.json() : null,
        ),
        fetch(`${base}/telemetry/latest?device=${encodeURIComponent(this.device)}&code=4SD_REM`).then((x) =>
          x.ok ? x.json() : null,
        ),
      ]);

      const text = t?.value;
      if (typeof text === 'string' && text.length) {
        this.display = text;
        this.cdr.markForCheck();
        return;
      }

      const rem = Number(r?.value);
      if (Number.isFinite(rem)) {
        this.display = this.formatMMSS(rem);
        this.cdr.markForCheck();
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
    const base = this.apiBase.replace(/\/+$/, '');
    const res = await fetch(`${base}${path}`, {
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
    if (this.busy) return;
    this.busy = true;
    this.cdr.markForCheck();
    try {
      await this.post('/pi2/timer/set', { device: this.device, seconds: this.setSeconds });
    } finally {
      this.busy = false;
      this.cdr.markForCheck();
    }
  }

  async applyAddSeconds(): Promise<void> {
    if (this.busy) return;
    this.busy = true;
    this.cdr.markForCheck();
    try {
      await this.post('/pi2/timer/add-seconds-config', { device: this.device, addSeconds: this.addSeconds });
    } finally {
      this.busy = false;
      this.cdr.markForCheck();
    }
  }

  async start(): Promise<void> {
    if (this.busy) return;
    this.busy = true;
    this.cdr.markForCheck();
    try {
      await this.post('/pi2/timer/run', { device: this.device, running: true });
    } finally {
      this.busy = false;
      this.cdr.markForCheck();
    }
  }

  async stop(): Promise<void> {
    if (this.busy) return;
    this.busy = true;
    this.cdr.markForCheck();
    try {
      await this.post('/pi2/timer/run', { device: this.device, running: false });
    } finally {
      this.busy = false;
      this.cdr.markForCheck();
    }
  }

  async reset(): Promise<void> {
    if (this.busy) return;
    this.busy = true;
    this.cdr.markForCheck();
    try {
      await this.post('/pi2/timer/reset', { device: this.device });
      this.blinkSuppressed = false;
      this.display = '00:00';
      this.cdr.markForCheck();
    } finally {
      this.busy = false;
      this.cdr.markForCheck();
    }
  }

  async pressBtn(): Promise<void> {
    if (this.display === '00:00') {
      this.blinkSuppressed = true;
      this.cdr.markForCheck();
    }
    await this.post('/pi2/btn/press', { device: this.device });
  }
}