import { Component, Input, NgZone, OnDestroy, OnInit, Inject, PLATFORM_ID } from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';

type Snapshot = {
  device: string;
  system_state?: string | null;
  alarm_active?: boolean;
  alarm_reason?: string | null;
  people_inside?: number;
  db_on?: boolean | null;
};

@Component({
  selector: 'app-security-status',
  imports: [CommonModule],
  standalone: true,
  templateUrl: './security-status.html',
  styleUrls: ['./security-status.css'],
})
export class SecurityStatus implements OnInit, OnDestroy {
  @Input({ required: true }) apiBase = 'http://localhost:5000';
  @Input({ required: true }) device = 'PI1';
  @Input() deviceName?: string;

  systemState: string | null = null;
  alarmActive = false;
  alarmReason: string | null = null;
  peopleInside = 0;
  dbOn: boolean | null = null;
  connected = false;

  private es?: EventSource;

  constructor(
    @Inject(PLATFORM_ID) private platformId: object,
    private zone: NgZone,
  ) {}

  ngOnInit(): void {
    if (!isPlatformBrowser(this.platformId)) return;
    this.loadSnapshot();
    this.openSse();
  }

  ngOnDestroy(): void {
    try { this.es?.close(); } catch {}
  }

  get mappedState(): string {
    return this.mapState(this.systemState);
  }

  get stateClass(): string {
    const s = this.mappedState;
    if (s === 'DISARMED')    return 'disarmed';
    if (s === 'ARMED')       return 'armed';
    if (s === 'ALARMED')     return 'alarmed';
    if (s === 'EXIT_DELAY')  return 'exit';
    if (s === 'ENTRY_DELAY') return 'entry';
    return 'unknown';
  }

  mapState(s: string | null): string {
    const v = (s || '').toUpperCase();
    if (!v) return 'Unknown';
    if (v.includes('DISARM')) return 'DISARMED';
    if (v.includes('EXIT'))   return 'EXIT_DELAY';
    if (v.includes('ENTRY'))  return 'ENTRY_DELAY';
    if (v.includes('ARMED'))  return 'ARMED';
    if (v.includes('ALARM'))  return 'ALARMED';
    return v;
  }

  private async loadSnapshot(): Promise<void> {
    try {
      const res = await fetch(`${this.apiBase}/state?device=${encodeURIComponent(this.device)}`);
      const data = (await res.json()) as Snapshot;
      this.applySnapshot(data);
    } catch {}
  }

  private openSse(): void {
    const url = `${this.apiBase}/events?device=${encodeURIComponent(this.device)}`;
    this.es = new EventSource(url);

    this.es.onopen = () => this.zone.run(() => (this.connected = true));

    this.es.addEventListener('snapshot', (e: MessageEvent) => {
      this.zone.run(() => {
        try { this.applySnapshot(JSON.parse(e.data) as Snapshot); } catch {}
      });
    });

    this.es.addEventListener('evt', (e: MessageEvent) => {
      this.zone.run(() => {
        try {
          const evt = JSON.parse(e.data) as any;
          const code = String(evt.code || '');
          const value = evt.value;
          if (code === 'ALARM_STATE')    this.systemState = String(value);
          if (code === 'ALARM')          this.alarmActive = !!value;
          if (code === 'ALARM_REASON')   this.alarmReason = String(value);
          if (code === 'PEOPLE_INSIDE')  this.peopleInside = Number(value) || 0;
          if (code === 'DB')             this.dbOn = !!value;
        } catch {}
      });
    });

    this.es.onerror = () => {
      this.zone.run(() => (this.connected = false));
      try { this.es?.close(); } catch {}
      setTimeout(() => this.openSse(), 1500);
    };
  }

  getPeopleArray(): number[] {
    return Array.from({ length: Math.min(this.peopleInside, 8) }, (_, i) => i);
  }

  private applySnapshot(s: Snapshot): void {
    if (s.system_state  !== undefined) this.systemState  = s.system_state  ?? null;
    if (s.alarm_active  !== undefined) this.alarmActive  = !!s.alarm_active;
    if (s.alarm_reason  !== undefined) this.alarmReason  = s.alarm_reason  ?? null;
    if (s.people_inside !== undefined) this.peopleInside = Number(s.people_inside) || 0;
    if (s.db_on         !== undefined) this.dbOn         = s.db_on == null ? null : !!s.db_on;
  }
}