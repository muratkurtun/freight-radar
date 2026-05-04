import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiBaseService } from '../../core/http/api-base.service';
import { Feedback, FeedbackCreate } from '../../core/models/feedback.model';

@Injectable({ providedIn: 'root' })
export class FeedbackService {
  private api = inject(ApiBaseService);

  submit(signalId: string, payload: FeedbackCreate): Observable<Feedback> {
    return this.api.post<Feedback>(`/signals/${signalId}/feedback`, payload);
  }

  history(signalId: string): Observable<Feedback[]> {
    return this.api.get<Feedback[]>(`/signals/${signalId}/feedback`);
  }
}
