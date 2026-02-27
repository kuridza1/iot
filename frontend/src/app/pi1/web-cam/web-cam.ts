import { Component } from '@angular/core';

@Component({
  selector: 'app-web-cam',
  imports: [],
  templateUrl: './web-cam.html',
  styleUrls: ['./web-cam.css', '../../../widget-frame.css'],
})

export class WebCam {
    url = 'http://192.168.107.148:8080/?action=stream';
  }
