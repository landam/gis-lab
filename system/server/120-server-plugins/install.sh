#
### SERVER PLUGINS ###
#

for plugin in /vagrant/user/plugins/server/*.*; do
	gislab_print_info "Running server plugin '$(basename $plugin)'"
	GISLAB_INSTALL_ACTION=$GISLAB_INSTALL_ACTION $plugin
	echo "$(gislab_config_header)" >> /etc/gislab/server-plugin-$(basename $plugin).done
done


# vim: set syntax=sh ts=4 sts=4 sw=4 noet: