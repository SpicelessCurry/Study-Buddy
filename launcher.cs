using System;
using System.Diagnostics;
using System.IO;
using System.Threading;

namespace StudyBuddyLauncher
{
    class Program
    {
        static void Main(string[] args)
        {
            Console.Title = "Study Buddy - AI Study Assistant";
            Console.ForegroundColor = ConsoleColor.Cyan;
            Console.WriteLine(@"
    ╔══════════════════════════════════════════════════╗
    ║                                                  ║
    ║       📚  S T U D Y   B U D D Y  📚             ║
    ║       AI-Powered RAG Study Assistant              ║
    ║                                                  ║
    ╚══════════════════════════════════════════════════╝
            ");
            Console.ResetColor();

            string appDir = AppDomain.CurrentDomain.BaseDirectory;
            string runScript = Path.Combine(appDir, "run.py");

            if (!File.Exists(runScript))
            {
                // Try parent directory if inside a subfolder
                string parentScript = Path.Combine(Directory.GetParent(appDir).FullName, "run.py");
                if (File.Exists(parentScript))
                {
                    appDir = Directory.GetParent(appDir).FullName;
                    runScript = parentScript;
                }
            }

            Console.WriteLine("  🚀 Starting Study Buddy application...");
            Console.WriteLine("  📂 Working Directory: " + appDir);

            string pythonExe = FindPython();
            if (string.IsNullOrEmpty(pythonExe))
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine("  ❌ Error: Python 3 was not found on this system.");
                Console.WriteLine("  Please install Python 3.10+ from https://python.org and add it to PATH.");
                Console.ResetColor();
                Console.WriteLine("\n  Press any key to exit...");
                Console.ReadKey();
                return;
            }

            Console.ForegroundColor = ConsoleColor.Green;
            Console.WriteLine("  🐍 Python found: " + pythonExe);
            Console.ResetColor();
            Console.WriteLine("  🌐 Opening browser at http://127.0.0.1:5000 ...");
            Console.WriteLine("  " + new string('═', 50));
            Console.WriteLine();

            ProcessStartInfo psi = new ProcessStartInfo
            {
                FileName = pythonExe,
                Arguments = "\"" + runScript + "\"",
                WorkingDirectory = appDir,
                UseShellExecute = false,
                RedirectStandardInput = false,
                RedirectStandardOutput = false,
                RedirectStandardError = false,
                CreateNoWindow = false
            };

            try
            {
                using (Process proc = Process.Start(psi))
                {
                    proc.WaitForExit();
                }
            }
            catch (Exception ex)
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine("  ❌ Error launching application: " + ex.Message);
                Console.ResetColor();
                Console.WriteLine("\n  Press any key to exit...");
                Console.ReadKey();
            }
        }

        static string FindPython()
        {
            // 1. Check current PATH
            string[] pathDirs = (Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator);
            foreach (string dir in pathDirs)
            {
                try
                {
                    string candidate = Path.Combine(dir.Trim(), "python.exe");
                    if (File.Exists(candidate))
                        return candidate;
                }
                catch { }
            }

            // 2. Check standard Windows Python installation directories
            string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string[] knownPaths = new string[]
            {
                Path.Combine(localAppData, @"Programs\Python\Python313\python.exe"),
                Path.Combine(localAppData, @"Programs\Python\Python312\python.exe"),
                Path.Combine(localAppData, @"Programs\Python\Python311\python.exe"),
                Path.Combine(localAppData, @"Programs\Python\Python310\python.exe"),
                @"C:\Python313\python.exe",
                @"C:\Python312\python.exe",
                @"C:\Python311\python.exe",
                @"C:\Python310\python.exe"
            };

            foreach (string path in knownPaths)
            {
                if (File.Exists(path))
                    return path;
            }

            return null;
        }
    }
}
