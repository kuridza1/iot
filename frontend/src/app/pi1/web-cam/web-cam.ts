import { Component } from '@angular/core';

@Component({
  selector: 'app-web-cam',
  imports: [],
  templateUrl: './web-cam.html',
  styleUrls: ['./web-cam.css', '../../../widget-frame.css'],
})

export class WebCam {
    url = 'http://localhost:5000/camera/pi1';
  }
