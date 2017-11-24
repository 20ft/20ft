mkdir -p /usr/local/bin/
mkdir -p /usr/local/share/man/man1

# pull the ambassador image
docker pull tfnz/tf:latest

# fetch and install the 'root' tf script
curl -s https://20ft.nz/tf > /usr/local/bin/tf 
chmod +x /usr/local/bin/tf
curl -s https://20ft.nz/tf.1 > /usr/local/share/man/man1/tf.1

# create 'child' scripts
apps=(tfvolumes tfdomains tfacctbak tfresources tfcache)
for app in ${apps[*]}; do
	ln -f -s /usr/local/bin/tf  /usr/local/bin/$app
	curl -s https://20ft.nz/$app.1 > /usr/local/share/man/man1/$app.1
done

# set up completion
if [ "${SHELL:(-4)}" == "fish" ]; then
	touch ~/.config/fish/config.fish
	echo 'complete -c tfvolumes -a "list create destroy"
	complete -c tfdomains -a "list prepare claim release" ' >> ~/.config/fish/config.fish
	source ~/.config/fish/config.fish
else
	echo 'complete -W "list create destroy" tfvolumes
	complete -W "list prepare claim release" tfdomains' >> ~/.bash_profile
	source ~/.bash_profile
fi
