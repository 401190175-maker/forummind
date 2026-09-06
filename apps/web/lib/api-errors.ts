/** API 客户端统一错误类型。 */

/** 未配置 NEXT_PUBLIC_API_BASE_URL 时抛出。 */
export class ApiConfigError extends Error {
  constructor(message = "未配置 NEXT_PUBLIC_API_BASE_URL，请参考 .env.example") {
    super(message);
    this.name = "ApiConfigError";
  }
}

/** HTTP 非 2xx 或网络失败时抛出。status 为 0 表示网络层失败。 */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}
