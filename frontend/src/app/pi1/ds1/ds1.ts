import { Component, Input, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';

type CmdResult = { ok: boolean; error?: string };

@Component({
  selector: 'app-ds1',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './ds1.html',
  styleUrls: ['./ds1.css', '../../../widget-frame.css'],
})
export class Ds1 implements OnDestroy {
  @Input({ required: true }) apiBase = 'http://localhost:5000';
  @Input({ required: true }) device = 'PI1';
  @Input() deviceName?: string;

  busy = false;
  lastOk: boolean | null = null;
  lastError = '';

  // DS1=true => UNLOCKED
  lockState: boolean | null = null;

  animating = false;
  private abort?: AbortController;

  ngOnDestroy(): void {
    this.abort?.abort();
  }

  async setDs1(unlocked: boolean): Promise<void> {
    if (this.busy) return;

    this.busy = true;
    this.animating = true;
    this.lastOk = null;
    this.lastError = '';

    // optimistički prikaz (odmah)
    this.lockState = unlocked;

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
          value: unlocked, // DS1=true => unlocked
        }),
      });

      const data = (await res.json()) as CmdResult;
      if (!res.ok || !data.ok) {
        this.lastOk = false;
        this.lastError = data.error || `HTTP ${res.status}`;
        return;
      }

      this.lastOk = true;
    } catch (e: any) {
      if (e?.name !== 'AbortError') {
        this.lastOk = false;
        this.lastError = 'Network error';
      }
    } finally {
      this.busy = false;
      setTimeout(() => (this.animating = false), 500);
    }
  }
}