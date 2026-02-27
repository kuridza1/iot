// src/app/pi1/ds1/ds1.ts
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
import { WsService, CmdResult } from '../../ws.service';

@Component({
  selector: 'app-ds1',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './ds1.html',
  styleUrls: ['./ds1.css', '../../../widget-frame.css'],
})
export class Ds1 implements OnInit, OnChanges, OnDestroy {
  @Input({ required: true }) apiBase = 'http://localhost:5000';
  @Input({ required: true }) device: 'PI1' | 'PI2' | 'PI3' = 'PI1';

  // NEW: which door actuator/sensor this instance controls/tracks
  // - On PI1 you pass 'DS1'
  // - On PI2 you pass 'DS2'
  @Input() doorCode: 'DS1' | 'DS2' = 'DS1';

  busy = false;
  lastOk: boolean | null = null;
  lastError = '';

  // true => UNLOCKED / OPEN (as you already interpret)
  lockState: boolean | null = null;

  animating = false;

  private abort?: AbortController;
  private subs = new Subscription();
  private hideTimer?: any;

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
      this.ws.evt.subscribe((evt: any) => {
        // Optional: if your events include device, keep instance separation strict
        const evtDevice = String(evt?.device || '');
        if (evtDevice && evtDevice !== this.device) return;

        const code = String(evt?.code || '').toUpperCase();
        if (code !== this.doorCode) return;

        this.lockState = evt?.value == null ? null : !!evt.value;
        this.cdr.detectChanges();
      }),
    );

    this.subs.add(
      this.ws.cmdResult.subscribe((msg: CmdResult) => {
        // Optional: if cmd_result includes device, keep instance separation strict
        const msgDevice = String((msg as any)?.device || '');
        if (msgDevice && msgDevice !== this.device) return;

        const cmd = String(msg?.cmd || '').toUpperCase();
        // If server includes cmd, match current instance's doorCode; if missing, accept any.
        if (cmd && cmd !== this.doorCode) return;

        this.lastOk = !!msg.ok;
        this.lastError = msg.ok ? '' : (msg.error || 'Command failed');

        if (this.hideTimer) clearTimeout(this.hideTimer);
        this.hideTimer = setTimeout(() => {
          this.lastOk = null;
          this.lastError = '';
          this.cdr.detectChanges();
        }, 2000);

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

    // IMPORTANT: treat device/doorCode change as a different instance state
    if (
      (ch['device'] && !ch['device'].firstChange) ||
      (ch['doorCode'] && !ch['doorCode'].firstChange)
    ) {
      this.ws.setDevice(this.device);
      this.lockState = null;
      this.lastOk = null;
      this.lastError = '';
      this.cdr.detectChanges();
    }
  }

  ngOnDestroy(): void {
    this.abort?.abort();
    this.subs.unsubscribe();
    if (this.hideTimer) clearTimeout(this.hideTimer);
  }

  async setDoor(unlocked: boolean): Promise<void> {
    if (this.busy) return;

    this.busy = true;
    this.animating = true;

    this.lastOk = null;
    this.lastError = '';

    // Optimistic UI
    this.lockState = unlocked;
    this.cdr.detectChanges();

    this.abort?.abort();
    this.abort = new AbortController();

    try {
      const res = await fetch(`${this.apiBase}/cmd`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: this.abort.signal,
        body: JSON.stringify({
          device: this.device,
          cmd: this.doorCode,     // NEW: DS1 or DS2 depending on instance
          value: unlocked,
        }),
      });

      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as any;
        this.lastOk = false;
        this.lastError = data?.error || `HTTP ${res.status}`;
        this.cdr.detectChanges();
      }
    } catch (e: any) {
      if (e?.name !== 'AbortError') {
        this.lastOk = false;
        this.lastError = 'Network error';
        this.cdr.detectChanges();
      }
    } finally {
      this.busy = false;
      setTimeout(() => {
        this.animating = false;
        this.cdr.detectChanges();
      }, 500);
    }
  }

  async setDs1(unlocked: boolean): Promise<void> {
    return this.setDoor(unlocked);
  }
}