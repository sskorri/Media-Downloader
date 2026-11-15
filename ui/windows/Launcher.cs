using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Windows.Forms;

internal static class Launcher
{
    // ProcessStartInfo on .NET Framework accepts a single Windows command line.
    private static string QuoteArgument(string value)
    {
        var quoted = new StringBuilder("\"");
        int backslashes = 0;
        foreach (char c in value)
        {
            if (c == '\\')
            {
                backslashes++;
                continue;
            }
            int count = c == '"' ? backslashes * 2 + 1 : backslashes;
            quoted.Append('\\', count).Append(c);
            backslashes = 0;
        }
        return quoted.Append('\\', backslashes * 2).Append('"').ToString();
    }

    private static int Run(string file, string arguments, string root, bool visible)
    {
        var start = new ProcessStartInfo(file, arguments) {
            WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = !visible
        };
        using (var process = Process.Start(start))
        {
            process.WaitForExit();
            return process.ExitCode;
        }
    }

    private static string ProjectPython(string root)
    {
        string venv = Path.Combine(root, ".venv");
        string python = Path.Combine(venv, "Scripts", "python.exe");
        string pythonw = Path.Combine(venv, "Scripts", "pythonw.exe");
        string ready = Path.Combine(venv, ".media-downloader-ready");
        // A second double-click must not start another pip or venv writer.
        using (var setupLock = new Mutex(false, @"Local\MediaDownloaderEnvironmentSetup"))
        {
            try { setupLock.WaitOne(); }
            catch (AbandonedMutexException) { /* A previous setup exited early. */ }
            try
            {
                DateTime requirements = new[] { Path.Combine(root, "requirements.txt"),
                    Path.Combine(root, "ui", "requirements.txt") }.Select(File.GetLastWriteTimeUtc).Max();
                if (File.Exists(pythonw) && File.Exists(ready) && File.GetLastWriteTimeUtc(ready) >= requirements)
                    return pythonw;

                // Source checkouts may already have an initialized environment.
                bool installed = File.Exists(python) && File.Exists(pythonw) && !File.Exists(ready)
                    && Run(python, "-I -B -c \"import importlib.util as u; " +
                        "assert all(u.find_spec(n) for n in ('webview','clr','yt_dlp','rich','spotdl'))\"", root, false) == 0;
                if (!installed)
                {
                    string command = Path.Combine(Environment.SystemDirectory, "cmd.exe");
                    if (Run(command, @"/d /c ui\windows\setup.cmd", root, true) != 0)
                        throw new ApplicationException("Setup could not prepare the local Python environment. " +
                            "Open a terminal in the app folder and run ui\\windows\\setup.cmd for details.");
                }
                File.WriteAllText(ready, "");
                return pythonw;
            }
            finally { setupLock.ReleaseMutex(); }
        }
    }

    [STAThread]
    private static int Main(string[] args)
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string runtime = Path.Combine(root, "runtime");
        try
        {
            string bundled = Path.Combine(runtime, "pythonw.exe");
            bool hasRuntime = File.Exists(bundled);
            var start = new ProcessStartInfo {
                FileName = hasRuntime ? bundled : ProjectPython(root),
                WorkingDirectory = root,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardError = true,
                StandardErrorEncoding = Encoding.UTF8,
                Arguments = "-E -s -B -X utf8 -m ui.gui " + string.Join(" ", args.Select(QuoteArgument))
            };
            if (hasRuntime)
                start.EnvironmentVariables["PATH"] = Path.Combine(runtime, "bin") +
                    Path.PathSeparator + start.EnvironmentVariables["PATH"];
            using (Process process = Process.Start(start))
            {
                string errors = process.StandardError.ReadToEnd();
                process.WaitForExit();
                if (process.ExitCode != 0)
                {
                    if (errors.Length > 3000) errors = errors.Substring(errors.Length - 3000);
                    MessageBox.Show(string.IsNullOrWhiteSpace(errors)
                        ? "The application exited with code " + process.ExitCode : errors,
                        "Media Downloader", MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
                return process.ExitCode;
            }
        }
        catch (Exception error)
        {
            MessageBox.Show(error.Message, "Media Downloader",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
