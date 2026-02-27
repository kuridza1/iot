import { Component, Input } from '@angular/core';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-grafana-embed',
  template: `
    <div *ngIf="safeUrl; else empty" class="widget-frame">
      <iframe
        [src]="safeUrl"
        width="100%"
        height="840px"
        frameborder="0"
        z-index="10000"
      ></iframe>
    </div>

    <ng-template #empty>
      <div>No dashboard selected.</div>
    </ng-template>
  `,
  styleUrls: ['grafana.css'],
  imports: [CommonModule]
})
export class GrafanaEmbedComponent {
  safeUrl: SafeResourceUrl | null = null;

  constructor(private sanitizer: DomSanitizer) {}

  @Input() set url(v: string | null) {
    this.safeUrl = v
      ? this.sanitizer.bypassSecurityTrustResourceUrl(v)
      : null;
  }
}