import '@testing-library/jest-dom'

// jsdom has no EventSource. Components that open the SSE stream
// (LiveEventFeed) construct one on mount, which would crash the render tree.
if (!('EventSource' in globalThis)) {
  class MockEventSource {
    static readonly CONNECTING = 0
    static readonly OPEN = 1
    static readonly CLOSED = 2
    onmessage: ((e: MessageEvent) => void) | null = null
    onerror: ((e: Event) => void) | null = null
    onopen: ((e: Event) => void) | null = null
    readyState = MockEventSource.CONNECTING
    url: string
    constructor(url: string) {
      this.url = url
    }
    addEventListener(): void {}
    removeEventListener(): void {}
    close(): void {
      this.readyState = MockEventSource.CLOSED
    }
  }
  // @ts-expect-error — test shim
  globalThis.EventSource = MockEventSource
}
