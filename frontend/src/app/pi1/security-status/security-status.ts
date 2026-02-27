// src/app/pi1/security-status/security-status.ts
import {
  Component,
  Input,
  OnDestroy,
  OnInit,
  OnChanges,
  SimpleChanges,
  Inject,
  PLATFORM_ID,
  ChangeDetectorRef,
} from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Subscription } from 'rxjs';
import { WsService, Snapshot, PinResult } from '../../ws.service';

@Component({
  selector: 'app-security-status',
  imports: [CommonModule],
  standalone: true,
  templateUrl: './security-status.html',
  styleUrls: ['./security-status.css', '../../../widget-frame.css'],
})
export class SecurityStatus implements OnInit, OnChanges, OnDestroy {
  @Input({ required: true }) apiBase = 'http://localhost:5000';
  @Input({ required: true }) device = 'PI1';

  systemState: string | null = null;
  alarmActive = false;
  alarmReason: string | null = null;
  peopleInside = 0;
  dbOn: boolean | null = null;
  connected = false;

  private subs = new Subscription();

  constructor(
    @Inject(PLATFORM_ID) private platformId: object,
    private ws: WsService,
    private cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    if (!isPlatformBrowser(this.platformId)) return;

    this.ws.ensureConnected(this.apiBase, this.device);
    this.ws.setDevice(this.device);

    this.subs.add(
      this.ws.connected.subscribe((v) => {
        this.connected = v;
        this.cdr.detectChanges();
      }),
    );

    // Initial + whenever server emits snapshot
    this.subs.add(
      this.ws.snapshot.subscribe((s: Snapshot) => {
        this.applySnapshot(s);
        this.cdr.detectChanges();
      }),
    );

    this.subs.add(
      this.ws.evt.subscribe((evt: any) => {
        const code = String(evt?.code || '');
        const value = evt?.value;

        if (code === 'ALARM_STATE') {
          this.systemState = value == null ? null : String(value);
          this.alarmActive = this.mapState(this.systemState) === 'ALARMED';
        }

        if (code === 'ALARM_REASON') this.alarmReason = value == null ? null : String(value);
        if (code === 'PEOPLE_INSIDE') this.peopleInside = Number(value) || 0;
        if (code === 'DB') this.dbOn = value == null ? null : !!value;

        this.cdr.detectChanges();
      }),
    );

    // React immediately to PIN result:
    //  - If ok => set DISARMED (or whatever your AlarmService uses)
    //  - If fail => show ENTRY_DELAY/ALARMED only if your backend will emit those;
    //    but we still force a refresh snapshot to avoid "static" UI.
    this.subs.add(
      this.ws.pinResult.subscribe((pr: PinResult) => {
        // Fast UI reaction: force snapshot refresh from the shared stream.
        // Your server already emits snapshot(device) after /alarm/pin, so this is mostly redundant,
        // but it ensures the UI updates even if only pin_result arrives first.
        // If you want purely optimistic UI, uncomment the mapping below.

        // Optimistic mapping (optional):
        // if (pr.ok) {
        //   this.systemState = 'DISARMED';
        //   this.alarmActive = false;
        //   this.alarmReason = null;
        // }

        this.cdr.detectChanges();
      }),
    );
  }

  ngOnChanges(ch: SimpleChanges): void {
    if (!isPlatformBrowser(this.platformId)) return;

    if (ch['apiBase'] && !ch['apiBase'].firstChange) {
      this.ws.ensureConnected(this.apiBase, this.device);
      this.ws.setDevice(this.device);
    }

    if (ch['device'] && !ch['device'].firstChange) {
      this.ws.setDevice(this.device);
      this.cdr.detectChanges();
    }
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
  }

  get mappedState(): string {
    return this.mapState(this.systemState);
  }

  get stateClass(): string {
    const s = this.mappedState;
    if (s === 'DISARMED') return 'disarmed';
    if (s === 'ARMED') return 'armed';
    if (s === 'ALARMED') return 'alarmed';
    if (s === 'EXIT_DELAY') return 'exit';
    if (s === 'ENTRY_DELAY') return 'entry';
    return 'unknown';
  }

  mapState(s: string | null): string {
    const v = (s || '').toUpperCase();
    if (!v) return 'Unknown';
    if (v.includes('DISARM')) return 'DISARMED';
    if (v.includes('EXIT')) return 'EXIT_DELAY';
    if (v.includes('ENTRY')) return 'ENTRY_DELAY';
    if (v.includes('ARMED')) return 'ARMED';
    if (v.includes('ALARM')) return 'ALARMED';
    return v;
  }

  getPeopleArray(): number[] {
    return Array.from({ length: Math.min(this.peopleInside, 8) }, (_, i) => i);
  }

  private applySnapshot(s: Snapshot): void {
    if (s.system_state !== undefined) this.systemState = s.system_state ?? null;
    if (s.alarm_active !== undefined) this.alarmActive = !!s.alarm_active;
    if (s.alarm_reason !== undefined) this.alarmReason = s.alarm_reason ?? null;
    if (s.people_inside !== undefined) this.peopleInside = Number(s.people_inside) || 0;
    if (s.db_on !== undefined) this.dbOn = s.db_on == null ? null : !!s.db_on;
  }
}