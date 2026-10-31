• The Strata GUI is open now, and the Coder model is loaded in it and shows as ready.
  Why the script failed: the Coder server I started earlier was still holding port 8080, so the second run stopped with "port 8080 is already in use". I stopped that ser
  ver before opening the app.
  Opening the GUI


  • Run open -a Strata, or double-click /Applications/Strata.app.
  • Choose coder-iq1_m in the model list and press Load. I triggered the same load call from the command line, and the GUI reports it as ready.
  • It runs the patched engine, with 131072 context and vision on.
  • The GUI serves the model on its own port (18500 this time) with a generated API key, so use the GUI's chat. Don't point other tools at port 8080.
  Script or GUI


  • Use one or the other. Both load the 58 GB model, which doesn't fit twice in 36 GB of RAM, and the script's default port is 8080.
  • The GUI refuses to load a model while a script-started server is running.
  • To start the script while the GUI is open, give it another port and drop --open:

  /Applications/Strata.app/Contents/Resources/control/python/bin/python3.12 \
    /Applications/Strata.app/Contents/Resources/control/serve/server.py \
    --engine strata \
    --config ~/.local/share/strata/install/strata-coder-iq1_m.json \
    --port 8090 --host 127.0.0.1
  • Add --api-key <your key> if you want the server to require a key. The usage text you pasted lists that option.
  • Everything else is already in the config file: the model paths, --mmap-experts, an expert cache of 64, context 131072 and vision.
  Don't change the config


  • The config's exe points at /Users/hirendave/models/strata/Strata/build-metal/strata. The GUI and the script both depend on that patched engine, so don't delete the f
  older.
  • To use the script plainly, first quit the GUI model: Unload in the GUI, or quit the app.
  The install job for IQ3_S also shows an old error in the GUI's job list ("engine exited… strata-iq3_s.log"). That's from an earlier attempt, not from this load. I test
  ed IQ3_S on the patched engine earlier and it generated correct answers.
