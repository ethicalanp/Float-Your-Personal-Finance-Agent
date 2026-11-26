export function cx(...args: unknown[]): string {
  return args
    .flat()
    .filter((x) => typeof x === "string" && x.length > 0)
    .join(" ");
}

export function sortCx<T extends Record<string, any>>(obj: T): T {
  return obj;
}
