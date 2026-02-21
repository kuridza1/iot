import { Injectable, NgZone } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class TelemetryService {
  private state$ = new BehaviorSubject<Record<string, any>>({});

  private es?: EventSource;
  private baseUrl?: string;

  private reconnectTimer?: any;
  private reconnectDelayMs = 500;

  constructor(private zone: NgZone) {}

  connect(baseUrl: string): void {
    if (this.es && this.baseUrl === baseUrl) return;

    this.baseUrl = baseUrl;
    this.cleanup();

    this.zone.runOutsideAngular(() => {
      const es = new EventSource(`${baseUrl}/events`);
      this.es = es;

      const scheduleReconnect = () => {
        if (this.reconnectTimer) return;

        const delay = this.reconnectDelayMs;
        this.reconnectDelayMs = Math.min(8000, Math.floor(this.reconnectDelayMs * 1.7));

        this.reconnectTimer = setTimeout(() => {
          this.reconnectTimer = undefined;
          if (this.baseUrl) this.connect(this.baseUrl);
        }, delay);
      };

      es.addEventListener('open', () => {
        this.reconnectDelayMs = 500;
      });

      es.addEventListener('snapshot', (e: any) => {
        try {
          const snap = JSON.parse(e.data || '{}');
          this.zone.run(() => this.state$.next(snap));
        } catch {}
      });

      es.onmessage = (e) => {
        try {
          const ev = JSON.parse(e.data || '{}');
          const key = `${ev.device}:${ev.code}`;
          this.zone.run(() => {
            this.state$.next({ ...this.state$.value, [key]: ev });
          });
        } catch {}
      };

      es.onerror = () => {
        try { es.close(); } catch {}
        scheduleReconnect();
      };
    });
  }

  getState(): Observable<Record<string, any>> {
    return this.state$.asObservable();
  }

  disconnect(): void {
    this.baseUrl = undefined;
    this.cleanup();
  }

  private cleanup(): void {
    try { this.es?.close(); } catch {}
    this.es = undefined;

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = undefined;
    }

    this.reconnectDelayMs = 500;
  }
}