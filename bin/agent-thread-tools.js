#!/usr/bin/env node
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const ROOT = path.resolve(__dirname, "..");
const VERSION = fs.readFileSync(path.join(ROOT, "VERSION"), "utf8").trim();

const PYTHON_TOOLS = new Map([
  ["health", "agent-thread-health.py"],
  ["handoff-summary", "agent-thread-handoff-summary.py"],
  ["handoff-marker", "agent-thread-handoff-marker.py"],
  ["session-archive", "agent-thread-session-archive.py"],
  ["visual-archive", "agent-thread-visual-archive.py"],
  ["recover", "agent-thread-recover.py"],
  ["reference", "agent-thread-reference.py"],
  ["hook", "agent-thread-hook.py"],
]);

const HOOK_COMMAND = "agent-thread-tools hook";
const THRESHOLD_PATTERN = /^\d+(\.\d+)?\s*[km]?$|^\d+(\.\d+)?\s*%$/i;

const HELP = `agent-thread-tools ${VERSION}

Usage:
  agent-thread-tools health [args...]
  agent-thread-tools handoff-summary [args...]
  agent-thread-tools handoff-marker [args...]
  agent-thread-tools session-archive [args...]
  agent-thread-tools visual-archive [args...]
  agent-thread-tools recover [args...]
  agent-thread-tools reference init|commit [--project DIR] [-m MESSAGE]
  agent-thread-tools install-skill [--agent codex|claude]
  agent-thread-tools install-skill --agent claude --auto-handoff [--at 250k]
  agent-thread-tools install-skill --agent claude --no-auto-handoff
  agent-thread-tools --version

Examples:
  agent-thread-tools health
  agent-thread-tools health --agent claude
  agent-thread-tools health check ~/.codex/sessions/YYYY/MM/DD/thread.jsonl
  agent-thread-tools handoff-summary ~/.codex/sessions/YYYY/MM/DD/thread.jsonl
  agent-thread-tools session-archive plan --older-than 30d --min-size 100MiB
  agent-thread-tools visual-archive scan ~/.codex/sessions/YYYY/MM/DD/thread.jsonl
`;

const SAFE_SKILL_INVOCATION = [
  "Use the installed `codex-thread-handoff` skill to create a repository-backed",
  "handoff for a new task. Do not use Codex's native Handoff or `handoff_thread`.",
  "If the skill is unavailable, stop and report that it must be installed.",
].join("\n");

function main(argv) {
  const [command, ...args] = argv;
  if (!command || command === "help" || command === "--help" || command === "-h") {
    process.stdout.write(HELP);
    return 0;
  }
  if (command === "--version" || command === "-v" || command === "version") {
    process.stdout.write(`${VERSION}\n`);
    return 0;
  }
  if (command === "install-skill") {
    if (skillAgent(args) !== "claude") {
      return installSkill();
    }
    const installed = installClaudeSkill();
    if (installed !== 0) {
      return installed;
    }
    if (args.includes("--auto-handoff")) {
      return configureAutoHandoff(optionValue(args, "--at") || "250k");
    }
    if (args.includes("--no-auto-handoff")) {
      return configureAutoHandoff(null);
    }
    return 0;
  }
  if (PYTHON_TOOLS.has(command)) {
    return runPythonTool(PYTHON_TOOLS.get(command), args);
  }
  process.stderr.write(`Unknown command: ${command}\n\n${HELP}`);
  return 1;
}

function runPythonTool(toolName, args) {
  const script = path.join(ROOT, "tools", toolName);
  for (const python of pythonCommands()) {
    const command = python.command;
    const pythonArgs = [...python.args, script, ...args];
    const result = spawnSync(command, pythonArgs, {
      cwd: process.cwd(),
      stdio: "inherit",
      env: process.env,
    });
    if (result.error && result.error.code === "ENOENT") {
      continue;
    }
    if (result.error) {
      process.stderr.write(`${result.error.message}\n`);
      return 1;
    }
    return result.status === null ? 1 : result.status;
  }
  process.stderr.write(
    "Python 3 is required. Install Python 3, then retry this command.\n"
  );
  return 1;
}

function pythonCommands() {
  if (process.platform === "win32") {
    return [
      { command: "py", args: ["-3"] },
      { command: "python", args: [] },
      { command: "python3", args: [] },
    ];
  }
  return [
    { command: "python3", args: [] },
    { command: "python", args: [] },
  ];
}

function skillAgent(args) {
  const index = args.indexOf("--agent");
  if (index !== -1 && args[index + 1]) {
    return args[index + 1];
  }
  const hasCodex = fs.existsSync(path.join(os.homedir(), ".codex"));
  const hasClaude = fs.existsSync(path.join(os.homedir(), ".claude"));
  return !hasCodex && hasClaude ? "claude" : "codex";
}

function optionValue(args, name) {
  const index = args.indexOf(name);
  return index !== -1 ? args[index + 1] : undefined;
}

// Adds (threshold given) or removes (null) the auto-handoff hooks in ~/.claude/settings.json,
// leaving every other setting and hook untouched.
function configureAutoHandoff(threshold) {
  if (threshold !== null && !THRESHOLD_PATTERN.test(threshold.trim())) {
    process.stderr.write("--at must look like 150k, 150000, 1m, or 60%\n");
    return 1;
  }
  const settingsFile = path.join(os.homedir(), ".claude", "settings.json");
  let settings = {};
  if (fs.existsSync(settingsFile)) {
    try {
      settings = JSON.parse(fs.readFileSync(settingsFile, "utf8"));
    } catch (error) {
      process.stderr.write(`Could not read ${settingsFile} (${error.message}); it was not changed.\n`);
      return 1;
    }
    fs.copyFileSync(settingsFile, `${settingsFile}.agent-thread-tools.bak`);
  }
  settings.hooks = settings.hooks || {};
  for (const event of ["Stop", "PreCompact"]) {
    const groups = (settings.hooks[event] || [])
      .map((group) => ({
        ...group,
        hooks: (group.hooks || []).filter(
          (hook) => !(typeof hook.command === "string" && hook.command.startsWith(HOOK_COMMAND))
        ),
      }))
      .filter((group) => group.hooks.length > 0);
    settings.hooks[event] = groups;
  }
  if (threshold !== null) {
    settings.hooks.Stop.push({
      matcher: "",
      hooks: [{ type: "command", command: `${HOOK_COMMAND} claude-stop --at ${threshold.trim()}`, timeout: 30 }],
    });
    settings.hooks.PreCompact.push({
      matcher: "",
      hooks: [{ type: "command", command: `${HOOK_COMMAND} claude-precompact`, timeout: 120 }],
    });
  }
  for (const event of ["Stop", "PreCompact"]) {
    if (settings.hooks[event].length === 0) {
      delete settings.hooks[event];
    }
  }
  if (Object.keys(settings.hooks).length === 0) {
    delete settings.hooks;
  }
  fs.mkdirSync(path.dirname(settingsFile), { recursive: true });
  fs.writeFileSync(settingsFile, `${JSON.stringify(settings, null, 2)}\n`);
  process.stdout.write(
    threshold !== null
      ? `\nAuto-handoff is on: after a turn ends with the context past ${threshold.trim()} tokens, ` +
          "Claude runs /thread-handoff once and asks you to run /clear.\n" +
          "Sessions started from now on use it; restart a running session. Turn it off with: " +
          "agent-thread-tools install-skill --agent claude --no-auto-handoff\n"
      : "\nAuto-handoff is off.\n"
  );
  return 0;
}

function installClaudeSkill() {
  const claudeHome = path.join(os.homedir(), ".claude");
  if (!fs.existsSync(claudeHome)) {
    process.stderr.write("Open Claude Code once so ~/.claude exists, then retry.\n");
    return 1;
  }
  try {
    const source = path.join(ROOT, "skills", "thread-handoff");
    const target = path.join(claudeHome, "skills", "thread-handoff");
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.rmSync(target, { recursive: true, force: true });
    fs.cpSync(source, target, { recursive: true });
    // Outside a plugin, Claude Code does not fill in ${CLAUDE_PLUGIN_ROOT}; use this package.
    const skillFile = path.join(target, "SKILL.md");
    fs.writeFileSync(
      skillFile,
      fs.readFileSync(skillFile, "utf8").split("${CLAUDE_PLUGIN_ROOT}").join(ROOT)
    );
    process.stdout.write(
      `Installed thread-handoff to ${target}\n\n` +
        "Invoke it in Claude Code with: /thread-handoff\n" +
        "Check session health with: agent-thread-tools health --agent claude\n"
    );
    return 0;
  } catch (error) {
    process.stderr.write(`Failed to install thread-handoff: ${error.message}\n`);
    return 1;
  }
}

function installSkill() {
  const codexHome = path.join(os.homedir(), ".codex");
  if (!fs.existsSync(codexHome)) {
    process.stderr.write("Open Codex once so ~/.codex exists, then retry.\n");
    return 1;
  }
  const skillsDir = path.join(codexHome, "skills");

  try {
    fs.mkdirSync(skillsDir, { recursive: true });
    const source = path.join(ROOT, "codex-skills", "codex-thread-handoff");
    const sourceSkill = path.join(source, "SKILL.md");
    const target = path.join(skillsDir, "codex-thread-handoff");
    const targetSkill = path.join(target, "SKILL.md");

    fs.rmSync(target, { recursive: true, force: true });
    fs.cpSync(source, target, { recursive: true });

    const sourceSkillContents = fs.readFileSync(sourceSkill);
    const targetSkillContents = fs.readFileSync(targetSkill);
    if (!sourceSkillContents.equals(targetSkillContents)) {
      process.stderr.write(
        "Failed to install codex-thread-handoff: SKILL.md verification failed\n"
      );
      return 1;
    }

    process.stdout.write(
      `Installed codex-thread-handoff to ${target}\n\n` +
        "Invoke it with:\n" +
        `${SAFE_SKILL_INVOCATION}\n\n` +
        "After upgrading agent-thread-tools, rerun `agent-thread-tools install-skill` to refresh the copied skill.\n" +
        "If the updated skill is not visible, reload Codex or start a new task.\n"
    );
    return 0;
  } catch (error) {
    process.stderr.write(
      `Failed to install codex-thread-handoff: ${error.message}\n`
    );
    return 1;
  }
}

process.exitCode = main(process.argv.slice(2));
