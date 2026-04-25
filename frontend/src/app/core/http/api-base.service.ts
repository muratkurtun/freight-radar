import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

type ParamValue = string | number | boolean | null | undefined;
type ParamsInput = Record<string, ParamValue>;

/**
 * Thin wrapper over HttpClient:
 *  - prefixes paths with the configured API base URL
 *  - strips null / undefined / empty query params so the URL stays clean
 *
 * Feature services inject this instead of HttpClient directly so the
 * base URL and param handling live in one place.
 */
@Injectable({ providedIn: 'root' })
export class ApiBaseService {
  private http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  get<T>(path: string, params?: ParamsInput): Observable<T> {
    return this.http.get<T>(this.url(path), { params: this.toParams(params) });
  }

  post<T>(path: string, body: unknown, params?: ParamsInput): Observable<T> {
    return this.http.post<T>(this.url(path), body, { params: this.toParams(params) });
  }

  put<T>(path: string, body: unknown): Observable<T> {
    return this.http.put<T>(this.url(path), body);
  }

  delete<T>(path: string): Observable<T> {
    return this.http.delete<T>(this.url(path));
  }

  private url(path: string): string {
    const p = path.startsWith('/') ? path : `/${path}`;
    return `${this.base}${p}`;
  }

  private toParams(input?: ParamsInput): HttpParams {
    let params = new HttpParams();
    if (!input) return params;
    for (const [key, value] of Object.entries(input)) {
      if (value !== null && value !== undefined && value !== '') {
        params = params.set(key, String(value));
      }
    }
    return params;
  }
}
