import type { Instrumentation } from "next";

/** Server-side error reporting: one structured line per unhandled request error, visible in Vercel logs. No request bodies or user data. */
export const onRequestError: Instrumentation.onRequestError = async (err, request, context) => {
  const e = err as { message?: string; digest?: string };
  console.error(
    JSON.stringify({
      level: "error",
      msg: e.message ?? "unknown error",
      digest: e.digest,
      path: request.path,
      method: request.method,
      route: context.routePath,
      routeType: context.routeType,
    }),
  );
};
