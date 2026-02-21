import { Injectable, NgZone } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class TelemetryService {
  private state$ = new BehaviorSubject<Record<string, any>>({});

  constructor(private zone: NgZone) {}

  connect(baseUrl: string) {
    const es = new EventSource(`${baseUrl}/events`);
    es.addEventListener('snapshot', (e: any) => {
      const snap = JSON.parse(e.data || '{}');
      this.zone.run(() => this.state$.next(snap));
    });
    es.onmessage = (e) => {
      const ev = JSON.parse(e.data || '{}');
      const key = `${ev.device}:${ev.code}`;
      this.zone.run(() => {
        this.state$.next({ ...this.state$.value, [key]: ev });
      });
    };
    return es;
  }

  getState() {
    return this.state$.asObservable();
  }
}