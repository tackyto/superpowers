#!/usr/bin/env python3
"""Windows verification for run-hook.cmd's bash discovery.

The CMD half of the polyglot wrapper only runs on Windows, so nothing in the
Linux suites reaches it. What it has to get right is which bash it picks:
`where bash` on a Windows box with WSL installed finds
C:\\Windows\\System32\\bash.exe, the WSL launcher, which cannot open a Windows
path and exits 127. That is neither the designed "run the hook" nor the
designed "skip it silently".

The two hardcoded Git for Windows paths are patched out of a *copy* of the
wrapper so the later branches become reachable. Patching a copy keeps the
production file free of a test-only seam -- it is an upstream-owned file, and
every line added to it is conflict surface at the next merge.

Its output stays ASCII on purpose: a Japanese Windows console is cp932, and
Python raises UnicodeEncodeError on the first character it cannot encode.

Run it from Git Bash on Windows:

    python3 tests/hooks/verify-windows-dispatch.py

Exits 0 when every check passes, 1 otherwise.
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
WRAPPER = os.path.join(REPO_ROOT, "hooks", "run-hook.cmd")

SYSTEM32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
GIT_STANDARD = r"C:\Program Files\Git"
GIT_STANDARD_X86 = r"C:\Program Files (x86)\Git"

FAILURES = []


def check(description, condition, detail=""):
    if condition:
        print("  [PASS] %s" % description)
        return True
    print("  [FAIL] %s" % description)
    if detail:
        for line in str(detail).splitlines():
            print("         %s" % line)
    FAILURES.append(description)
    return False


def write_bytes(path, text):
    """Write LF-terminated text. CRLF in a bash script is a syntax error."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(text.replace("\r\n", "\n").encode("utf-8"))


class Workspace:
    """A hooks directory holding a wrapper and the hook it dispatches to."""

    def __init__(self, root, patch_standard_paths, hook_exit=0):
        self.root = root
        self.hooks = os.path.join(root, "hooks")
        self.marker = os.path.join(root, "ran.txt")
        os.makedirs(self.hooks, exist_ok=True)

        with open(WRAPPER, "rb") as handle:
            wrapper = handle.read().decode("utf-8")
        if patch_standard_paths:
            # Point the two hardcoded branches at directories that do not
            # exist, so discovery has to fall through to the later ones.
            wrapper = wrapper.replace(GIT_STANDARD_X86, os.path.join(root, "AbsentGitX86"))
            wrapper = wrapper.replace(GIT_STANDARD, os.path.join(root, "AbsentGit"))
        write_bytes(os.path.join(self.hooks, "run-hook.cmd"), wrapper)

        # The hook reports that it ran, using only bash builtins so it works
        # under any bash the wrapper might pick.
        write_bytes(os.path.join(self.hooks, "probe-hook"),
                    '#!/usr/bin/env bash\nprintf "ran\\n" > "$DISPATCH_MARKER"\n'
                    'exit %d\n' % hook_exit)

    @property
    def wrapper(self):
        return os.path.join(self.hooks, "run-hook.cmd")

    def dispatch(self, path_entries):
        """Run the wrapper with a PATH we control. Returns (exit code, ran?)."""
        if os.path.exists(self.marker):
            os.remove(self.marker)
        environment = dict(os.environ)
        environment["PATH"] = os.pathsep.join(path_entries)
        environment["DISPATCH_MARKER"] = self.marker.replace("\\", "/")
        # cmd.exe by absolute path: several checks hand the child a PATH that
        # deliberately excludes System32, and resolving the interpreter through
        # that PATH would fail before the wrapper ever ran.
        completed = subprocess.run(
            [os.path.join(SYSTEM32, "cmd.exe"), "/c", self.wrapper, "probe-hook"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment,
        )
        return completed, os.path.exists(self.marker)


def fake_bash_dir(root, name, flavour, delegate_to=None):
    """A directory holding a bash shim that reports `flavour` for `uname -o`.

    With `delegate_to`, anything else is handed to a real bash; without it, the
    shim mimics WSL's failure on a Windows path.
    """
    directory = os.path.join(root, name)
    os.makedirs(directory, exist_ok=True)
    if delegate_to:
        tail = '"%s" %%*\r\nexit /b %%ERRORLEVEL%%\r\n' % delegate_to
    else:
        tail = ('echo /bin/bash: %~1: No such file or directory 1>&2\r\n'
                'exit /b 127\r\n')
    script = ('@echo off\r\n'
              'if "%~1"=="-c" (\r\n'
              '    echo ' + flavour + '\r\n'
              '    exit /b 0\r\n'
              ')\r\n') + tail
    with open(os.path.join(directory, "bash.bat"), "wb") as handle:
        handle.write(script.encode("utf-8"))
    return directory


def where_only_dir(root):
    """A PATH entry with where.exe and nothing else, so `where bash` finds none."""
    directory = os.path.join(root, "WhereOnly")
    os.makedirs(directory, exist_ok=True)
    shutil.copy2(os.path.join(SYSTEM32, "where.exe"), directory)
    return directory


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------

def check_environment():
    print("Environment")
    check("running on native Windows", sys.platform == "win32",
          "sys.platform is %r - run this from Git Bash on Windows, not WSL" % sys.platform)
    wsl = os.path.join(SYSTEM32, "bash.exe")
    check("WSL's bash.exe is on this machine, so the bad branch is reachable",
          os.path.exists(wsl),
          "%s is absent - this machine cannot exercise the WSL case" % wsl)
    check("Git for Windows is installed at the standard path",
          os.path.exists(os.path.join(GIT_STANDARD, "bin", "bash.exe")),
          "%s\\bin\\bash.exe is absent" % GIT_STANDARD)


def check_untouched_wrapper(root):
    """The normal case must keep working: Git at the standard path, branch one."""
    print("Unpatched wrapper, real environment")
    workspace = Workspace(os.path.join(root, "real"), patch_standard_paths=False)
    completed, ran = workspace.dispatch([SYSTEM32])
    check("hook runs", ran, describe(completed))
    check("exit code is 0", completed.returncode == 0, describe(completed))


def check_wsl_is_rejected(root):
    """The bug: WSL's bash gets picked and dies on the Windows path."""
    print("PATH offers only WSL's bash")
    workspace = Workspace(os.path.join(root, "wsl"), patch_standard_paths=True)
    completed, ran = workspace.dispatch([SYSTEM32])
    check("hook does not run", not ran, describe(completed))
    check("exit code is 0", completed.returncode == 0, describe(completed))
    # Rejecting WSL means never launching it: its error output on stderr is the
    # evidence that the wrapper handed it the hook and waited for it to fail.
    check("WSL's bash is never invoked", completed.stderr.strip() == b"",
          describe(completed))


def check_exit_code_propagates(root):
    """A hook that fails must not be reported as a success.

    `exit /b %ERRORLEVEL%` inside a parenthesised if-block expands at parse
    time, so it carries the value from before the hook ran -- every hook looked
    like it succeeded, on every Windows branch.
    """
    print("Unpatched wrapper, hook exits 3")
    workspace = Workspace(os.path.join(root, "exitcode"), patch_standard_paths=False,
                          hook_exit=3)
    completed, ran = workspace.dispatch([SYSTEM32])
    check("hook runs", ran, describe(completed))
    check("wrapper reports the hook's exit code", completed.returncode == 3,
          describe(completed))


def check_git_derivation(root):
    """A Git install the hardcoded branches do not cover is still usable."""
    print("PATH offers git, and only WSL's bash")
    workspace = Workspace(os.path.join(root, "derive"), patch_standard_paths=True)
    git_cmd = os.path.join(GIT_STANDARD, "cmd")
    if not os.path.exists(os.path.join(git_cmd, "git.exe")):
        check("git.exe is where derivation expects it", False, "%s\\git.exe absent" % git_cmd)
        return
    completed, ran = workspace.dispatch([SYSTEM32, git_cmd])
    check("hook runs via the bash derived from git", ran, describe(completed))
    check("exit code is 0", completed.returncode == 0, describe(completed))


def check_msys_is_accepted(root):
    """MSYS2 and Cygwin are what the PATH branch exists to serve."""
    print("PATH offers an MSYS-family bash")
    workspace = Workspace(os.path.join(root, "msys"), patch_standard_paths=True)
    shim = fake_bash_dir(root, "MsysShim", "Msys",
                         delegate_to=os.path.join(GIT_STANDARD, "bin", "bash.exe"))
    completed, ran = workspace.dispatch([shim, where_only_dir(root)])
    check("hook runs", ran, describe(completed))
    check("exit code is 0", completed.returncode == 0, describe(completed))


def check_no_bash_at_all(root):
    """Upstream's documented behaviour: skip the hook, never fail the session."""
    print("PATH offers no bash and no git")
    workspace = Workspace(os.path.join(root, "none"), patch_standard_paths=True)
    completed, ran = workspace.dispatch([where_only_dir(root)])
    check("hook does not run", not ran, describe(completed))
    check("exit code is 0", completed.returncode == 0, describe(completed))


def describe(completed):
    return "exit=%d\nstdout=%s\nstderr=%s" % (
        completed.returncode,
        completed.stdout.decode("utf-8", "replace").strip(),
        completed.stderr.decode("utf-8", "replace").strip(),
    )


def main():
    print("verify-windows-dispatch.py - run-hook.cmd bash discovery")
    print()
    check_environment()
    with tempfile.TemporaryDirectory() as root:
        for section in (check_untouched_wrapper, check_exit_code_propagates,
                        check_wsl_is_rejected, check_git_derivation,
                        check_msys_is_accepted, check_no_bash_at_all):
            print()
            section(root)
    print()
    if FAILURES:
        print("%d check(s) failed." % len(FAILURES))
        return 1
    print("All run-hook.cmd dispatch checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
