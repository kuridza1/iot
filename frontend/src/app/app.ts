import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { PANES, PiId } from './model/smart-house.model';
import { FloorplanComponent } from './floorplan/floorplan.component';
import { GrafanaEmbedComponent } from './grafana-embed/grafana-embed.component';
import { Timer } from './timer/timer';
import { Ds1 } from './pi1/ds1/ds1';
import { Dms } from './pi1/dms/dms';
import { SecurityStatus } from './pi1/security-status/security-status';
import { Dl } from './pi1/dl/dl';
import { WebCam } from './pi1/web-cam/web-cam';
import { LcdComponent } from './pi3/lcd/lcd.component';
import { BrgbComponent } from './pi3/brgb/brgb.component';

@Component({
  selector: 'app-root',
  standalone: true,
  templateUrl: './app.html',
  imports: [CommonModule, FloorplanComponent, GrafanaEmbedComponent, Ds1, Dms, WebCam, SecurityStatus, LcdComponent, BrgbComponent, Timer],
})
export class App {
  selectedPi: PiId = 'PI1';
  apiBase = 'http://localhost:5000';

  get grafanaUrl(): string | null {
    const pane = PANES.find(p => p.id === this.selectedPi);
    if (!pane) return null;

    const url = new URL(pane.grafana.dashboardUrl);
    Object.entries(pane.grafana.params ?? {}).forEach(([k, v]) => url.searchParams.set(k, v));
    return url.toString();
  }
}