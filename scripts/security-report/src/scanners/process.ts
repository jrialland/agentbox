export interface ProcessResult {
  stdout: string;
  stderr: string;
  exitCode: number;
  timedOut: boolean;
  durationMs: number;
}

export interface CommandResult {
  stdout: string;
  stderr: string;
  exitCode: number;
}

export type CommandRunner = (
  command: string,
  args: string[],
  cwd: string,
) => Promise<CommandResult>;

export async function runProcess(
  command: string,
  args: string[],
  options: { cwd: string; timeoutMs: number },
): Promise<ProcessResult> {
  const started = performance.now();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs);

  try {
    const proc = Bun.spawn([command, ...args], {
      cwd: options.cwd,
      stdout: "pipe",
      stderr: "pipe",
      signal: controller.signal,
    });
    const [stdout, stderr, exitCode] = await Promise.all([
      new Response(proc.stdout).text(),
      new Response(proc.stderr).text(),
      proc.exited,
    ]);
    return {
      stdout,
      stderr,
      exitCode,
      timedOut: controller.signal.aborted,
      durationMs: Math.round(performance.now() - started),
    };
  } catch (error) {
    return {
      stdout: "",
      stderr: error instanceof Error ? error.message : String(error),
      exitCode: -1,
      timedOut: controller.signal.aborted,
      durationMs: Math.round(performance.now() - started),
    };
  } finally {
    clearTimeout(timer);
  }
}

export const defaultCommandRunner: CommandRunner = async (command, args, cwd) => {
  const result = await runProcess(command, args, { cwd, timeoutMs: 30_000 });
  return {
    stdout: result.stdout,
    stderr: result.stderr,
    exitCode: result.exitCode,
  };
};

export async function commandVersion(
  command: string,
  args: string[],
  cwd: string,
): Promise<string> {
  const result = await runProcess(command, args, { cwd, timeoutMs: 20_000 });
  const firstLine = (result.stdout || result.stderr)
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find((line) => line.length > 0);
  const match = firstLine?.match(/\d+\.\d+\.\d+[\w.-]*/);
  return match?.[0] ?? "unknown";
}

export function tail(value: string, max = 2000): string {
  return value.length <= max ? value : value.slice(value.length - max);
}
