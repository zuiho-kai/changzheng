$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Speech
Add-Type -AssemblyName System.Web.Extensions
Add-Type -ReferencedAssemblies @('System.Speech', 'System.Web.Extensions') -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Speech.Synthesis;
using System.Speech.AudioFormat;
using System.Web.Script.Serialization;

public class SpeechMark {
    public int position;
    public int count;
    public double seconds;
    public string text;
}
public class LocalSpeechWorker {
    public static void Run() {
        var json = new JavaScriptSerializer();
        json.MaxJsonLength = 16000000;
        using (var synth = new SpeechSynthesizer()) {
            string line;
            while ((line = Console.ReadLine()) != null) {
                try {
                    var request = json.Deserialize<Dictionary<string, object>>(line);
                    if (request.ContainsKey("list")) {
                        var voices = new List<object>();
                        foreach (var installed in synth.GetInstalledVoices()) {
                            if (installed.Enabled) voices.Add(new { name = installed.VoiceInfo.Name, culture = installed.VoiceInfo.Culture.Name });
                        }
                        Console.WriteLine(json.Serialize(new { voices = voices }));
                        continue;
                    }
                    synth.SelectVoice((string)request["voice"]);
                    var marks = new List<SpeechMark>();
                    EventHandler<SpeakProgressEventArgs> handler = (sender, e) => {
                        lock (marks) marks.Add(new SpeechMark {position=e.CharacterPosition, count=e.CharacterCount, seconds=e.AudioPosition.TotalSeconds, text=e.Text});
                    };
                    synth.SpeakProgress += handler;
                    try {
                        using (var stream = new MemoryStream()) {
                            synth.SetOutputToAudioStream(stream, new SpeechAudioFormatInfo(16000, AudioBitsPerSample.Sixteen, AudioChannel.Mono));
                            synth.Speak((string)request["text"]);
                            synth.SetOutputToNull();
                            lock (marks) Console.WriteLine(json.Serialize(new {audio=Convert.ToBase64String(stream.ToArray()), sample_rate=16000, marks=marks}));
                        }
                    } finally { synth.SpeakProgress -= handler; }
                } catch (Exception e) {
                    Console.WriteLine(json.Serialize(new {error=e.Message}));
                }
            }
        }
    }
}
'@
[LocalSpeechWorker]::Run()
