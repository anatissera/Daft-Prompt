declare module "undici" {
  export class Agent {
    constructor(options?: {
      headersTimeout?: number;
      bodyTimeout?: number;
      connectTimeout?: number;
    });
  }
}
