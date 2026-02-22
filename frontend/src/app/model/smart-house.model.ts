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
    pathD: 'M 195 635 L 420 635 L 420 575 L 525 575 L 525 720 L 195 720 Z',
    labelPos: { x: 255, y: 640 },
    grafana: { dashboardUrl: 'http://localhost:3000/d/PI1_UID/pi1', params: { kiosk: '1' } },
  },
  {
    id: 'PI2',
    label: 'PI2',
    color: '#58ff68',
    pathD: 'M 470 25 L 470 340 L 400 340 L 400 575 L 525 575 L 525 725 L 555 725 L 580 770 L 620 788 L 670 788 L 715 771 L 742 725 L 765 725 L 765 25',
    labelPos: { x: 720, y: 410 },
    grafana: { dashboardUrl: 'http://localhost:3000/d/PI2_UID/pi2', params: { kiosk: '1' } },
  },
  {
    id: 'PI3',
    label: 'PI3',
    color: '#9fd0fe',
    pathD: 'M 150 120 L 150 345 L 35 345 L 35 620 L 307 620 L 307 565 L 380 565 L 380 340 L 470 340 L 470 100 Z',
    labelPos: { x: 255, y: 280 },
    grafana: { dashboardUrl: 'http://localhost:3000/d/PI3_UID/pi3', params: { kiosk: '1' } },
  },
];
export const ELEMENTS: HouseElement[] = [
  // PI3 primeri:
  { id: 'DHT1', label: 'Bedroom DHT', type: 'sensor', pi: 'PI3', xPct: 12, yPct: 58,
    grafana: { dashboardUrl: 'http://localhost:3000/d/PI3_UID/pi3', params: { kiosk: '1', 'var-code': 'DHT1' } } },
  { id: 'DHT2', label: 'Master DHT', type: 'sensor', pi: 'PI3', xPct: 20, yPct: 19,
    grafana: { dashboardUrl: 'http://localhost:3000/d/PI3_UID/pi3', params: { kiosk: '1', 'var-code': 'DHT2' } } },
  { id: 'IR', label: 'Infrared', type: 'sensor', pi: 'PI3', xPct: 17, yPct: 16,
    grafana: { dashboardUrl: 'http://localhost:3000/d/PI3_UID/pi3', params: { kiosk: '1', 'var-code': 'IR' } } },
  { id: 'BRGB', label: 'RGB Light', type: 'actuator', pi: 'PI3', xPct: 31, yPct: 28,
    grafana: { dashboardUrl: 'http://localhost:3000/d/PI3_UID/pi3', params: { kiosk: '1', 'var-code': 'BRGB' } } },
  { id: 'LCD', label: 'Living LCD', type: 'actuator', pi: 'PI3', xPct: 23, yPct: 45,
    grafana: { dashboardUrl: 'http://localhost:3000/d/PI3_UID/pi3', params: { kiosk: '1', 'var-code': 'LCD' } } },
  { id: 'DPIR3', label: 'Living PIR', type: 'sensor', pi: 'PI3', xPct: 23, yPct: 55,
    grafana: { dashboardUrl: 'http://localhost:3000/d/PI3_UID/pi3', params: { kiosk: '1', 'var-code': 'DPIR3' } } },
];
