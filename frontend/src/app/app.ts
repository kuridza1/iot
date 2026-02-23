import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { PANES, PiId } from './model/smart-house.model';
import { FloorplanComponent } from './floorplan/floorplan.component';
import { GrafanaEmbedComponent } from './grafana-embed/grafana-embed.component';
import { Ds1 } from './pi1/ds1/ds1';
import { Dms } from './pi1/dms/dms';
import { SecurityStatus } from './pi1/security-status/security-status';

@Component({
  selector: 'app-root',
  standalone: true,
  templateUrl: './app.html',
  imports: [CommonModule, FloorplanComponent, GrafanaEmbedComponent, Ds1, Dms, SecurityStatus],
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