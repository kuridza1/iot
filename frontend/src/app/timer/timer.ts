import {
  Component,
  Inject,
  NgZone,
  OnDestroy,
  OnInit,
  PLATFORM_ID,
  ChangeDetectorRef,
} from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { FormsModule } from '@angular/forms';

type TimerEvent = {
  device?: string;
  code?: string;
  value?: any;
};

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

  private es?: EventSource;
  private isBrowser: boolean;

  constructor(
    @Inject(PLATFORM_ID) platformId: Object,
    private zone: NgZone,
    private cdr: ChangeDetectorRef
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
  }

  async ngOnInit(): Promise<void> {
    if (!this.isBrowser) return;

    await this.loadInitialState();
    this.connectRealtime();
  }

  ngOnDestroy(): void {
    if (!this.isBrowser) return;
    this.cleanupRealtime();
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

 private reconnectTimer?: any;
  private reconnectDelayMs = 500;

  private connectRealtime(): void {
    if (!this.isBrowser) return;

    // uvek počisti
    this.cleanupRealtime();

    const url = 'http://localhost:5000/events';
    const es = new EventSource(url);
    this.es = es;

    const scheduleReconnect = () => {
      // izbegni beskonačno pravljenje novih konekcija
      if (this.reconnectTimer) return;

      const delay = this.reconnectDelayMs;
      this.reconnectDelayMs = Math.min(8000, Math.floor(this.reconnectDelayMs * 1.7));

      this.reconnectTimer = setTimeout(() => {
        this.reconnectTimer = undefined;
        this.connectRealtime();
      }, delay);
    };

    es.addEventListener('open', () => {
      // kad se konektuje, resetuj backoff
      this.reconnectDelayMs = 500;
    });

    es.addEventListener('snapshot', (e: any) => {
      try {
        const snap = JSON.parse(e.data || '{}');
        const kText = `${this.device}:4SD`;
        const kRem = `${this.device}:4SD_REM`;

        const text = snap?.[kText]?.value;
        const rem = Number(snap?.[kRem]?.value);

        this.zone.run(() => {
          if (typeof text === 'string' && text.length) {
            this.display = text;
          } else if (Number.isFinite(rem)) {
            this.display = this.formatMMSS(rem);
          }
          // u dev modu pomaže da “uhvati” promenu posle HMR
          setTimeout(() => this.cdr.detectChanges(), 0);
        });
      } catch {}
    });

    es.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data || '{}');
        const dev = String(ev.device ?? '').trim();
        if (dev && dev !== this.device) return;

        if (ev.code === '4SD') {
          const text = String(ev.value ?? '00:00');
          this.zone.run(() => {
            this.display = text;
            setTimeout(() => this.cdr.detectChanges(), 0);
          });
        } else if (ev.code === '4SD_REM') {
          const rem = Number(ev.value);
          if (!Number.isFinite(rem)) return;
          this.zone.run(() => {
            this.display = this.formatMMSS(rem);
            setTimeout(() => this.cdr.detectChanges(), 0);
          });
        }
      } catch {}
    };

    es.onerror = () => {
      // EventSource ponekad ne reconnectuje lepo u dev/HMR.
      // Ručno ga zatvaramo i pravimo novi.
      try { es.close(); } catch {}
      scheduleReconnect();
    };
  }

  private cleanupRealtime(): void {
    try { this.es?.close(); } catch {}
    this.es = undefined;

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = undefined;
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
  }

  async pressBtn(): Promise<void> {
    await this.post('/pi2/btn/press', { device: this.device });
  }
}