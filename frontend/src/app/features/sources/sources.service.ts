import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiBaseService } from '../../core/http/api-base.service';
import {
  PagedSources,
  Source,
  SourceCreate,
  SourceUpdate,
} from '../../core/models/source.model';

export interface SourcesQuery {
  limit?: number;
  offset?: number;
}

@Injectable({ providedIn: 'root' })
export class SourcesService {
  private api = inject(ApiBaseService);

  list(query: SourcesQuery = {}): Observable<PagedSources> {
    return this.api.get<PagedSources>('/sources', {
      limit: query.limit ?? 50,
      offset: query.offset ?? 0,
    });
  }

  create(payload: SourceCreate): Observable<Source> {
    return this.api.post<Source>('/sources', payload);
  }

  update(id: string, payload: SourceUpdate): Observable<Source> {
    return this.api.patch<Source>(`/sources/${id}`, payload);
  }

  remove(id: string): Observable<void> {
    return this.api.delete<void>(`/sources/${id}`);
  }
}
