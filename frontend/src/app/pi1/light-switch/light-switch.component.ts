// src/app/pi1/light-switch/light-switch.ts
import {
  Component,
  Input,
  OnDestroy,
  OnInit,
  OnChanges,
  SimpleChanges,
  Inject,
  PLATFORM_ID,
  NgZone,
  ChangeDetectionStrategy,
  ChangeDetectorRef,
} from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Subscription } from 'rxjs';
import { WsService, CmdResult } from '../../ws.service';

const AUTO_OFF_SEC = 10;

@Component({
  selector: 'app-light-switch',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './light-switch.component.html',
  styleUrls: ['./light-switch.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LightSwitch implements OnInit, OnChanges, OnDestroy {
  @Input({ required: true }) apiBase = 'http://localhost:5000';
  @Input({ required: true }) device = 'PI1';

  busy = false;
  lastOk: boolean | null = null;
  lastError = '';
  dlOn: boolean | null = null;

  readonly circumference = 2 * Math.PI * 25;
  dashOffset = 0;
  remainingSec = AUTO_OFF_SEC;

  private abort?: AbortController;
  private subs = new Subscription();
  private hideTimer?: ReturnType<typeof setTimeout>;
  private countdownTimer?: ReturnType<typeof setInterval>;
  private countdownStart = 0;

  constructor(
    @Inject(PLATFORM_ID) private platformId: object,
    private ws: WsService,
    private zone: NgZone,
    private cdr: ChangeDetectorRef,
  ) {}

  private mark(): void {
    this.cdr.markForCheck();
  }

  ngOnInit(): void {
    if (!isPlatformBrowser(this.platformId)) return;

    this.ws.ensureConnected(this.apiBase, this.device);
    this.ws.setDevice(this.device);

    this.subs.add(
      this.ws.snapshot.subscribe((snap: any) => {
        const dl = snap?.actuators?.DL;
        if (dl !== undefined) {
          this.dlOn = !!dl;
          if (this.dlOn) this.startCountdown();
          this.mark();
        }
      }),
    );

    this.subs.add(
      this.ws.evt.subscribe((evt: any) => {
        if (String(evt?.code || '') !== 'DL') return;
        const prev = this.dlOn;
        this.dlOn = evt?.value == null ? null : !!evt.value;
        if (this.dlOn && !prev) {
          this.startCountdown();
        } else if (!this.dlOn) {
          this.stopCountdown();
        }
        this.mark();
      }),
    );

    this.subs.add(
      this.ws.cmdResult.subscribe((msg: CmdResult) => {
        const cmd = String(msg?.cmd || '').toUpperCase();
        if (cmd && cmd !== 'DL') return;
        this.lastOk = !!msg.ok;
        this.lastError = msg.ok ? '' : (msg.error || 'Command failed');
        if (this.hideTimer) clearTimeout(this.hideTimer);
        this.hideTimer = setTimeout(() => {
          this.lastOk = null;
          this.lastError = '';
          this.mark();
        }, 2000);
        this.mark();
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
      this.dlOn = null;
      this.lastOk = null;
      this.lastError = '';
      this.stopCountdown();
      this.mark();
    }
  }

  ngOnDestroy(): void {
    this.abort?.abort();
    this.subs.unsubscribe();
    if (this.hideTimer) clearTimeout(this.hideTimer);
    this.stopCountdown();
  }

  activate(): void {
    this.sendDl(true);
  }

  private startCountdown(): void {
    this.stopCountdown();
    this.countdownStart = Date.now();
    this.remainingSec = AUTO_OFF_SEC;
    this.dashOffset = 0;

    this.zone.runOutsideAngular(() => {
      this.countdownTimer = setInterval(() => {
        const elapsed = (Date.now() - this.countdownStart) / 1000;
        const progress = Math.min(elapsed / AUTO_OFF_SEC, 1);
        this.dashOffset = this.circumference * progress;
        this.remainingSec = Math.max(0, Math.ceil(AUTO_OFF_SEC - elapsed));

        if (progress >= 1) {
          this.stopCountdown();
          this.dlOn = false;
        }

        this.zone.run(() => this.mark());
      }, 250);
    });
  }

  private stopCountdown(): void {
    if (this.countdownTimer) {
      clearInterval(this.countdownTimer);
      this.countdownTimer = undefined;
    }
    this.dashOffset = 0;
    this.remainingSec = AUTO_OFF_SEC;
  }

  private sendDl(on: boolean): void {
    if (this.busy) return;
    this.busy = true;
    this.lastOk = null;
    this.lastError = '';
    this.dlOn = on;
    if (on) this.startCountdown();
    this.mark();

    this.abort?.abort();
    this.abort = new AbortController();
    const signal = this.abort.signal;

    fetch(`${this.apiBase}/cmd`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal,
      body: JSON.stringify({ device: this.device, cmd: 'DL', value: on }),
    })
      .then(res => {
        if (!res.ok) {
          return res.json().catch(() => ({})).then((data: any) => {
            this.zone.run(() => {
              this.lastOk = false;
              this.lastError = data?.error || `HTTP ${res.status}`;
              this.dlOn = !on;
              this.stopCountdown();
              this.busy = false;
              this.mark();
            });
          });
        }
        this.zone.run(() => {
          this.busy = false;
          this.mark();
        });
        return Promise.resolve();
      })
      .catch((e: any) => {
        if (e?.name !== 'AbortError') {
          this.zone.run(() => {
            this.lastOk = false;
            this.lastError = 'Network error';
            this.dlOn = !on;
            this.stopCountdown();
            this.busy = false;
            this.mark();
          });
        }
      });
  }
}