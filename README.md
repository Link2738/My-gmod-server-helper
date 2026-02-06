# My-gmod-server-helper
Its just a small script/program to help me work on a gmod server.

It uses steamcmd to download addons either in a single or collection format and saves the .gma file for anothe program.

It then extracts the .gma file to its folder structure and parses it for .mdl files, or it can do multiple files/folders beh. 

Then it uses a modified version of a source engine helper program called crowbar (the specific one is cli based so i can run args to automate it) to decompile .mdl files so it can read the .qc and write a .lua file for items in the "pointshop 1" addon that includes bodygroups.

lastly it should spit out either one or multiple lua files that have all the information so you can put them into your pointshop and have them appear on the server. 
(Best bet is to make a collection of addons you want and have the server download them, then players download it and have the script make the files so you can put them and you should be good)

Forgot to mention this is mostly for playermodels, it makes lua files of all models but you should edit equips yourself to make sure nothing breaks with things like bodygroups
