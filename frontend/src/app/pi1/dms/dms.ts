// src/app/pi1/dms/dms.ts
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
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { WsService, PinResult } from '../../ws.service';

@Component({
  selector: 'app-dms',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './dms.html',
  styleUrls: ['./dms.css', '../../../widget-frame.css'],
})
export class Dms implements OnInit, OnChanges, OnDestroy {
  @Input({ required: true }) apiBase = 'http://localhost:5000';
  @Input({ required: true }) device = 'PI1';
  @Input() deviceName?: string;

  pin = '';
  busy = false;

  // drives the status message in dms.html
  lastOk: boolean | null = null;
  lastError = '';
  shake = false;

  private abort?: AbortController;
  private sub?: Subscription;

  // optional: hide message after some time
  private hideTimer?: any;

  constructor(
    @Inject(PLATFORM_ID) private platformId: object,
    private ws: WsService,
    private cdr: ChangeDetectorRef,
  ) {}

  get dots(): number[] {
    return [0, 1, 2, 3];
  }

  ngOnInit(): void {
    console.log('[DMS] ngOnInit', { apiBase: this.apiBase, device: this.device });
    console.log('[SEC] ngOnInit', { apiBase: this.apiBase, device: this.device });
    if (!isPlatformBrowser(this.platformId)) return;

    this.ws.ensureConnected(this.apiBase, this.device);
    this.ws.setDevice(this.device);

    this.sub = this.ws.pinResult.subscribe((msg: PinResult) => {
      // show result
      this.lastOk = !!msg.ok;
      this.lastError = msg.ok ? '' : (msg.error || 'PIN rejected');
      if (!msg.ok) this.triggerShake();

      // optional: auto-hide after 2.5s
      if (this.hideTimer) clearTimeout(this.hideTimer);
      this.hideTimer = setTimeout(() => {
        this.lastOk = null;
        this.lastError = '';
        this.cdr.markForCheck();
      }, 2500);

      this.cdr.markForCheck();
    });
  }

  ngOnChanges(ch: SimpleChanges): void {
    if (!isPlatformBrowser(this.platformId)) return;

    if (ch['apiBase'] && !ch['apiBase'].firstChange) {
      this.ws.ensureConnected(this.apiBase, this.device);
      this.ws.setDevice(this.device);
    }

    if (ch['device'] && !ch['device'].firstChange) {
      this.ws.setDevice(this.device);
      this.pin = '';
      this.lastOk = null;
      this.lastError = '';
      this.cdr.markForCheck();
    }
  }

  ngOnDestroy(): void {
    this.abort?.abort();
    this.sub?.unsubscribe();
    if (this.hideTimer) clearTimeout(this.hideTimer);
  }

  pressDigit(d: string): void {
    if (this.busy) return;

    // Only clear the previous message when starting a NEW attempt (first digit)
    if (this.pin.length === 0) {
      this.lastOk = null;
      this.lastError = '';
    }

    if (this.pin.length < 4) {
      this.pin += d;
      this.cdr.markForCheck();
    }

    if (this.pin.length === 4) {
      this.submit();
    }
  }

  backspace(): void {
    if (this.busy) return;

    this.pin = this.pin.slice(0, -1);

    // If user erased everything, clear the message too
    if (this.pin.length === 0) {
      this.lastOk = null;
      this.lastError = '';
    }

    this.cdr.markForCheck();
  }

  clear(): void {
    if (this.busy) return;

    this.pin = '';
    this.lastOk = null;
    this.lastError = '';
    this.cdr.markForCheck();
  }

  async submit(): Promise<void> {
    const p = this.pin.trim();
    if (!/^\d{4}$/.test(p)) {
      this.lastOk = false;
      this.lastError = 'PIN must be 4 digits';
      this.triggerShake();
      this.cdr.markForCheck();
      return;
    }

    this.ws.setDevice(this.device);

    this.busy = true;
    this.abort?.abort();
    this.abort = new AbortController();
    this.cdr.markForCheck();

    try {
      const res = await fetch(`${this.apiBase}/alarm/pin`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: this.abort.signal,
        body: JSON.stringify({
          device: this.device,
          device_name: this.deviceName ?? this.device,
          pin: p,
        }),
      });

      // WS pin_result is the source of truth. Only show hard HTTP errors.
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as any;
        this.lastOk = false;
        this.lastError = data?.error || `HTTP ${res.status}`;
        this.triggerShake();
      }

      // Clear input after submit, keep lastOk/lastError for the status message
      this.pin = '';
    } catch (e: any) {
      if (e?.name !== 'AbortError') {
        this.lastOk = false;
        this.lastError = 'Network error';
        this.triggerShake();
        this.pin = '';
      }
    } finally {
      this.busy = false;
      this.cdr.markForCheck();
    }
  }

  private triggerShake(): void {
    this.shake = true;
    setTimeout(() => {
      this.shake = false;
      this.cdr.markForCheck();
    }, 600);
  }
}