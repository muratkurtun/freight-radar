import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiBaseService } from '../../core/http/api-base.service';
import {
  PagedSignals,
  ReviewDecisionRequest,
  Signal,
} from '../../core/models/review.model';

@Injectable({ providedIn: 'root' })
export class ReviewsService {
  private api = inject(ApiBaseService);

  listPending(limit = 20, offset = 0): Observable<PagedSignals> {
    return this.api.get<PagedSignals>('/reviews/pending', { limit, offset });
  }

  decide(signalId: string, payload: ReviewDecisionRequest): Observable<Signal> {
    return this.api.post<Signal>(`/reviews/${signalId}`, payload);
  }
}
