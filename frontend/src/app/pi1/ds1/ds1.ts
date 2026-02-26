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
  @Input({ required: true }) device = 'PI1';

  busy = false;
  lastOk: boolean | null = null;
  lastError = '';

  // DS1=true => UNLOCKED / OPEN
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

    // (1) Track actual DS1 state from telemetry events (if PI emits DS1 events)
    this.subs.add(
      this.ws.evt.subscribe((evt: any) => {
        const code = String(evt?.code || '');
        if (code !== 'DS1') return;

        this.lockState = evt?.value == null ? null : !!evt.value;
        this.cdr.detectChanges();
      }),
    );

    // (2) Status message from cmd_result
    this.subs.add(
      this.ws.cmdResult.subscribe((msg: CmdResult) => {
        // If server includes cmd, match DS1; if missing, accept any cmd_result for this device.
        const cmd = String(msg?.cmd || '').toUpperCase();
        if (cmd && cmd !== 'DS1') return;

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

    if (ch['device'] && !ch['device'].firstChange) {
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

  async setDs1(unlocked: boolean): Promise<void> {
    if (this.busy) return;

    this.busy = true;
    this.animating = true;

    // Clear previous message for a new command
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
          cmd: 'DS1',
          value: unlocked, // true => OPEN / UNLOCKED
        }),
      });

      // If HTTP fails hard, show immediate error (WS may not arrive)
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
}