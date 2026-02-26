import { Component, Input, OnDestroy, OnInit, Inject, PLATFORM_ID, ChangeDetectorRef } from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Subscription } from 'rxjs';
import { WsService } from '../../ws.service';

@Component({
  selector: 'app-brgb',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './brgb.component.html',
  styleUrls: ['./brgb.component.css'],
})
export class BrgbComponent implements OnInit, OnDestroy {
  @Input() apiBase = 'http://localhost:5000';
  @Input() device = 'PI3';

  connected = false;
  busy = false;

  // live state
  r = false;
  g = false;
  b = false;

  lastOk: boolean | null = null;
  lastError = '';

  private sub = new Subscription();
  private sendTimer: any = null;
  private pending: { r: number; g: number; b: number } | null = null;

  constructor(
    @Inject(PLATFORM_ID) private platformId: object,
    private ws: WsService,
    private cdr: ChangeDetectorRef,
  ) {}

  ngOnInit(): void {
    if (!isPlatformBrowser(this.platformId)) return;

    // If you centrally manage WS in App, you can remove these two lines.
    this.ws.ensureConnected(this.apiBase, this.device);
    this.ws.setDevice(this.device);

    this.sub.add(this.ws.connected.subscribe(v => {
      this.connected = v;
      this.cdr.detectChanges();
    }));

    this.sub.add(this.ws.evt.subscribe(evt => {
      const code = String(evt?.code || '');
      if (code !== 'BRGB' && code !== 'BRGB_SET') return;

      const v = evt.value;
      if (!v || typeof v !== 'object') return;

      this.r = typeof v.r === 'boolean' ? v.r : !!v.r;
      this.g = typeof v.g === 'boolean' ? v.g : !!v.g;
      this.b = typeof v.b === 'boolean' ? v.b : !!v.b;
      this.cdr.detectChanges();
    }));

    this.sub.add(this.ws.cmdResult.subscribe(msg => {
      const cmd = String(msg?.cmd || '');
      if (cmd !== 'BRGB_SET' && cmd !== 'PI3_BRGB_SET') return;

      this.busy = false;
      this.lastOk = !!msg.ok;
      this.lastError = msg.error || '';
      this.cdr.detectChanges();

      window.setTimeout(() => {
        this.lastOk = null;
        this.lastError = '';
        this.cdr.detectChanges();
      }, 1200);
    }));
  }

  ngOnDestroy(): void {
    this.sub.unsubscribe();
    if (this.sendTimer) {
      clearTimeout(this.sendTimer);
      this.sendTimer = null;
    }
  }

  toggle(channel: 'r' | 'g' | 'b'): void {
    if (this.busy) return;

    if (channel === 'r') this.r = !this.r;
    if (channel === 'g') this.g = !this.g;
    if (channel === 'b') this.b = !this.b;

    this.queueSend();
  }

  private queueSend(): void {
    this.pending = { r: this.r ? 1 : 0, g: this.g ? 1 : 0, b: this.b ? 1 : 0 };

    if (this.sendTimer) clearTimeout(this.sendTimer);
    this.sendTimer = setTimeout(() => {
      this.sendTimer = null;
      void this.sendNow();
    }, 120);
  }

  private async sendNow(): Promise<void> {
    if (!this.pending) return;

    const payload = this.pending;
    this.pending = null;

    this.busy = true;
    this.lastOk = null;
    this.lastError = '';
    this.cdr.detectChanges();

    try {
      await this.ws.sendCmdHttp(this.device, 'BRGB_SET', payload);
      // busy will be cleared by cmd_result; fallback:
      window.setTimeout(() => {
        if (this.busy) {
          this.busy = false;
          this.cdr.detectChanges();
        }
      }, 2000);
    } catch (e: any) {
      this.busy = false;
      this.lastOk = false;
      this.lastError = String(e?.message || e || 'failed');
      this.cdr.detectChanges();
    }
  }
}