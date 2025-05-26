export class EventStreamManager {
  private eventSource: EventSource | null = null;
  private url: string;
  private onMessage: (data: any) => void;
  private onError: (error: Error) => void;
  private onConnect: () => void;
  private maxRetries: number = 3;
  private retryCount: number = 0;
  private retryDelay: number = 1000;

  constructor(
    url: string,
    onMessage: (data: any) => void,
    onError: (error: Error) => void,
    onConnect: () => void
  ) {
    this.url = url;
    this.onMessage = onMessage;
    this.onError = onError;
    this.onConnect = onConnect;
  }

  connect() {
    this.close();
    
    try {
      this.eventSource = new EventSource(this.url);
      
      this.eventSource.onopen = () => {
        this.retryCount = 0;
        this.onConnect();
      };
      
      this.eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.onMessage(data);
        } catch (err) {
          console.error("Error parsing event data:", err);
        }
      };
      
      this.eventSource.onerror = (error) => {
        if (this.eventSource?.readyState === EventSource.CLOSED) {
          if (this.retryCount < this.maxRetries) {
            this.retryCount++;
            const delay = this.retryDelay * Math.pow(1.5, this.retryCount);
            setTimeout(() => this.connect(), delay);
          } else {
            this.onError(new Error("Failed to connect after maximum retries"));
          }
        }
      };
    } catch (error) {
      this.onError(error as Error);
    }
  }

  close() {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }
}