declare module 'wxt/browser' {
  // Offline structural check only. Real WXT/WebExtension API compatibility is verified by npm typecheck/build.
  export const browser: any;
}

declare module '@webext-core/messaging' {
  type Fn = (...args: any[]) => any;
  type FnKeys<P> = { [K in keyof P]: P[K] extends Fn ? K : never }[keyof P];
  type Data<P, K extends FnKeys<P>> = P[K] extends (data: infer D) => any ? D : undefined;
  type Ret<P, K extends FnKeys<P>> = P[K] extends (...args: any[]) => infer R ? Awaited<R> : never;
  type Sender = { id?: string; tab?: { id?: number }; frameId?: number; documentId?: string; url?: string };
  export function defineExtensionMessaging<P>(): {
    sendMessage<K extends FnKeys<P>>(
      type: K,
      data: Data<P, K>,
      target?: number | { tabId: number; frameId?: number }
    ): Promise<Ret<P, K>>;
    onMessage<K extends FnKeys<P>>(
      type: K,
      callback: (message: { data: Data<P, K>; sender: Sender; type: K; timestamp: number }) => Ret<P, K> | Promise<Ret<P, K>>
    ): () => void;
  };
}

declare function defineBackground(main: (...args: any[]) => any): any;
declare function defineContentScript(config: any): any;

declare module 'vitest' {
  export const it: (name: string, fn: () => void | Promise<void>) => void;
  export const describe: (name: string, fn: () => void) => void;
  export const afterEach: (fn: () => void | Promise<void>) => void;
  export function expect<T>(value: T): {
    toBe(expected: unknown): void;
    toEqual(expected: unknown): void;
    toBeNull(): void;
    toBeGreaterThan(expected: number): void;
    not: { toBe(expected: unknown): void };
  };
}

declare module 'idb' {
  export interface DBSchema {}
  export type IDBPDatabase<T = unknown> = any;
  export function openDB<T = unknown>(name: string, version?: number, options?: any): Promise<IDBPDatabase<T>>;
  export function unwrap<T = any>(value: any): T;
}

declare module 'fake-indexeddb/auto' {}
declare module 'fake-indexeddb' {
  export function forceCloseDatabase(db: IDBDatabase): void;
}

declare module 'react' {
  export type ReactNode = any;
  export type SetStateAction<T> = T | ((previous: T) => T);
  export type Dispatch<T> = (value: T) => void;
  export function useState<T>(initial: T | (() => T)): [T, Dispatch<SetStateAction<T>>];
  export function useEffect(effect: () => void | (() => void), deps?: readonly unknown[]): void;
  export function useMemo<T>(factory: () => T, deps: readonly unknown[]): T;
  export function useCallback<T extends (...args: any[]) => any>(callback: T, deps: readonly unknown[]): T;
  export function useRef<T>(initial: T): { current: T };
  const React: { StrictMode: any };
  export default React;
}

declare module 'react/jsx-runtime' {
  export const Fragment: any;
  export function jsx(type: any, props: any, key?: any): any;
  export function jsxs(type: any, props: any, key?: any): any;
}

declare module 'react-dom/client' {
  export function createRoot(container: Element | DocumentFragment): { render(node: any): void; unmount(): void };
}

declare namespace JSX {
  interface IntrinsicElements { [elementName: string]: any; }
}
