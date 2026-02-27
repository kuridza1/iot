import {
  Component,
  Inject,
  Input,
  OnDestroy,
  OnInit,
  OnChanges,
  SimpleChanges,
  PLATFORM_ID,
  ChangeDetectorRef,
} from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { Subscription } from 'rxjs';
import { WsService } from '../../ws.service';

@Component({
  selector: 'app-dl',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './dl.html',
  styleUrls: ['./dl.css'],
})
export class Dl implements OnInit, OnChanges, OnDestroy {

  @Input({ required: true }) apiBase = 'http://localhost:5000';
  @Input({ required: true }) device = 'PI1';

  @Input() top = '50%';
  @Input() left = '50%';
  @Input() sizePx = 20;

  dlOn: boolean | null = null;

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

    // Initial state from snapshot
    this.subs.add(
      this.ws.snapshot.subscribe((snap: any) => {
        const dl = snap?.actuators?.DL;
        if (dl !== undefined) {
          this.dlOn = !!dl;
          this.cdr.detectChanges();
        }
      }),
    );

    // Live DL actuator events
    this.subs.add(
      this.ws.evt.subscribe((evt: any) => {
        if (String(evt?.code || '') !== 'DL') return;
        this.dlOn = evt?.value == null ? null : !!evt.value;
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
      this.dlOn = null;
      this.cdr.detectChanges();
    }
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
  }
}