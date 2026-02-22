import { Component, Input, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

type PinResult = { ok: boolean; error?: string };

@Component({
  selector: 'app-dms',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './dms.html',
  styleUrls: ['./dms.css'],
})
export class Dms implements OnDestroy {
  @Input({ required: true }) apiBase = 'http://localhost:5000';
  @Input({ required: true }) device = 'PI1';
  @Input() deviceName?: string;

  pin = '';
  busy = false;
  lastOk: boolean | null = null;
  lastError = '';
  shake = false;

  private abort?: AbortController;

  get dots(): number[] {
    return [0, 1, 2, 3];
  }

  get isFilled(): boolean {
    return /^\d{4}$/.test(this.pin);
  }

  ngOnDestroy(): void {
    this.abort?.abort();
  }

  pressDigit(d: string): void {
    if (this.pin.length < 4) {
      this.pin += d;
      this.lastOk = null;
      this.lastError = '';
    }
    if (this.pin.length === 4) {
      this.submit();
    }
  }

  backspace(): void {
    this.pin = this.pin.slice(0, -1);
    this.lastOk = null;
    this.lastError = '';
  }

  clear(): void {
    this.pin = '';
    this.lastOk = null;
    this.lastError = '';
  }

  async submit(): Promise<void> {
    const p = this.pin.trim();
    if (!/^\d{4}$/.test(p)) {
      this.triggerShake();
      this.lastOk = false;
      this.lastError = 'PIN must be 4 digits';
      return;
    }

    this.busy = true;
    this.lastOk = null;
    this.lastError = '';
    this.abort?.abort();
    this.abort = new AbortController();

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

      const data = (await res.json()) as PinResult;

      if (!res.ok || !data.ok) {
        this.lastOk = false;
        this.lastError = data.error || `HTTP ${res.status}`;
        this.triggerShake();
        this.pin = '';
        return;
      }

      this.lastOk = true;
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
    }
  }

  private triggerShake(): void {
    this.shake = true;
    setTimeout(() => (this.shake = false), 600);
  }
}