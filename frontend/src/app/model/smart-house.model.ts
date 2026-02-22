export type PiId = 'PI1' | 'PI2' | 'PI3';
export type ElementType = 'sensor' | 'actuator';

export interface HouseElement {
  id: string;          // npr. 'DUS1', 'DPIR3', 'BRGB'
  label: string;       // npr. 'Door Ultrasonic'
  type: ElementType;
  pi: PiId;
  // pozicija na slici u procentima (responsive)
  xPct: number;        // 0..100
  yPct: number;        // 0..100
  // grafana mapping
  grafana?: {
    dashboardUrl: string;   // ili base url + params
    // opciono: panelId, variable, query parami
    params?: Record<string, string>;
  };
}

export interface PiPane {
  id: PiId;
  label: string;
  color: string;      // hex
  pathD: string;      // SVG path in viewBox coordinates
  labelPos: { x: number; y: number }; // in viewBox coordinates
  grafana: { dashboardUrl: string; params?: Record<string, string> };
}

export const PANES: PiPane[] = [
  {
    id: 'PI1',
    label: 'PI1',
    color: '#ffbf58',
    pathD: 'M 152 620 L 308 620 L 308 565 L 380 565 L 380 702 L 152 702 Z',
    labelPos: { x: 340, y: 650 },
    grafana: { dashboardUrl: 'http://localhost:3000/d/PI1_UID/pi1', params: { kiosk: '1' } },
  },
  {
    id: 'PI2',
    label: 'PI2',
    color: '#58ff68',
    pathD: 'M 342 50 L 340 345 L 293 345 L 293 565 L 380 565 L 380 705 L 400 705 L 418 750 L 448 765 L 482 765 L 510 750 L 530 707 L 548 705 L 548 50 Z',
    labelPos: { x: 410, y: 500 },
    grafana: { dashboardUrl: 'http://localhost:3000/d/PI2_UID/pi2', params: { kiosk: '1' } },
  },
  {
    id: 'PI3',
    label: 'PI3',
    color: '#9fd0fe',
    pathD: 'M 147 120 L 147 345 L 32 345 L 32 620 L 310 620 L 310 565 L 293 565 L 293 345 L 340 345 L 340 120 Z',
    labelPos: { x: 185, y: 500 },
    grafana: { dashboardUrl: 'http://localhost:3000/d/PI3_UID/pi3', params: { kiosk: '1' } },
  },
];
export const ELEMENTS: HouseElement[] = [
];
