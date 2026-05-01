import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiBaseService } from '../../core/http/api-base.service';
import {
  PagedPlatformSources,
  PlatformSource,
  PlatformSourceCreate,
  PlatformSourceUpdate,
} from '../../core/models/source.model';

export interface PlatformSourcesQuery {
  limit?: number;
  offset?: number;
}

@Injectable({ providedIn: 'root' })
export class SourcePoolService {
  private api = inject(ApiBaseService);

  list(query: PlatformSourcesQuery = {}): Observable<PagedPlatformSources> {
    return this.api.get<PagedPlatformSources>('/platform/sources', {
      limit: query.limit ?? 50,
      offset: query.offset ?? 0,
    });
  }

  create(payload: PlatformSourceCreate): Observable<PlatformSource> {
    return this.api.post<PlatformSource>('/platform/sources', payload);
  }

  update(id: string, payload: PlatformSourceUpdate): Observable<PlatformSource> {
    return this.api.patch<PlatformSource>(`/platform/sources/${id}`, payload);
  }

  remove(id: string): Observable<void> {
    return this.api.delete<void>(`/platform/sources/${id}`);
  }
}
