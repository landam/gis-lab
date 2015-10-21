# -*- mode: ruby -*-
# vi: set ft=ruby :

require 'yaml'

# Vagrantfile API/syntax version. Don't touch unless you know what you're doing!
VAGRANTFILE_API_VERSION = "2"

Vagrant.require_version ">= 1.7.0"

CONFIG = Hash.new
# default GIS.lab server machine configuration file
conf = YAML.load_file('system/group_vars/all')
conf.each do |key, value|
  if not value.nil?
    CONFIG[key] = value
  end
end

# Configuration file for machine running under Vagrant provisioner.
# Use this file to override default GIS.lab configuration when
# using Vagrant provisioner.
if File.exist?('system/host_vars/gislab_vagrant')
  conf = YAML.load_file('system/host_vars/gislab_vagrant')
  conf.each do |key, value|
    if not value.nil?
      CONFIG[key] = value
    end
  end
end


Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  # http://cloud-images.ubuntu.com/vagrant/precise/current/precise-server-cloudimg-i386-vagrant-disk1.box
  # or
  # http://cloud-images.ubuntu.com/vagrant/precise/current/precise-server-cloudimg-amd64-vagrant-disk1.box

  # fix for https://github.com/ansible/ansible/issues/8644
  ENV['PYTHONIOENCODING'] = "utf-8"

  config.vm.box = "precise-canonical"
  config.vm.synced_folder '.', '/vagrant', disabled: true
  config.ssh.forward_agent = true


  # provisioning
  config.vm.define :gislab_vagrant do |server|
    server.vm.network "public_network", ip: CONFIG['GISLAB_NETWORK'] + ".5"

    # VirtualBox configuration
    server.vm.provider "virtualbox" do |vb, override|
      vb.customize ["modifyvm", :id, "--memory", CONFIG['GISLAB_SERVER_MEMORY']]
      vb.customize ["modifyvm", :id, "--cpus", CONFIG['GISLAB_SERVER_CPUS']]
      vb.customize ["modifyvm", :id, "--nictype1", "virtio"]
      vb.customize ["modifyvm", :id, "--nictype2", "virtio"]

      if CONFIG['GISLAB_SERVER_GUI_CONSOLE'] == true
        vb.gui = true
      end
    end

    # installation
    server.vm.provision "install", type: "ansible" do |ansible|
      ansible.playbook = "system/gislab.yml"
      if CONFIG['GISLAB_DEBUG_INSTALL'] == true
        ansible.verbose = "vv"
      end
      if CONFIG.has_key? 'GISLAB_ADMIN_PASSWORD'
        ansible.extra_vars = { GISLAB_ADMIN_PASSWORD: CONFIG['GISLAB_ADMIN_PASSWORD'] }
      end
    end

    # tests
    if CONFIG['GISLAB_TESTS_ENABLE'] == true
      server.vm.provision "test", type: "ansible" do |ansible|
        ansible.playbook = "system/test.yml"
        ansible.verbose = "vv"
      end
    end

  end
end
