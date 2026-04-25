export interface Page {
  limit: number;
  offset: number;
  total: number;
}

export interface Paged<T> {
  items: T[];
  page: Page;
}
