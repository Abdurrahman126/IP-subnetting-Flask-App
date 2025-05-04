from flask import Flask, render_template, request
import ipaddress

import os
import datetime


app = Flask(__name__)

@app.context_processor
def inject_now():
    return {'current_year': datetime.datetime.now().year}
template_dir = os.path.abspath('templates')
app = Flask(__name__, template_folder=template_dir)
def calculate_subnet_info(network_address):
    try:
        network = ipaddress.IPv4Network(network_address, strict=False)
        subnet_info = {
            'network_address': str(network.network_address),
            'broadcast_address': str(network.broadcast_address),
            'netmask': str(network.netmask),
            'prefix_length': network.prefixlen,
            'num_addresses': network.num_addresses,
            'usable_hosts': network.num_addresses - 2 if network.num_addresses > 2 else 0,
            'wildcard_mask': str(network.hostmask),
            'first_host': str(network.network_address + 1) if network.num_addresses > 2 else "N/A",
            'last_host': str(network.broadcast_address - 1) if network.num_addresses > 2 else "N/A"
        }
        
        return subnet_info, None
    except ValueError as e:
        return None, str(e)

def calculate_subnets(network_address, num_subnets=None, hosts_per_subnet=None):
    try:
        network = ipaddress.IPv4Network(network_address, strict=False)
        
        if hosts_per_subnet:
            required_bits = 0
            while (2 ** required_bits - 2) < int(hosts_per_subnet):
                required_bits += 1
            
            new_prefix = 32 - required_bits
            if new_prefix < network.prefixlen:
                return None, "The requested hosts per subnet exceed the available address space."
            
            subnets = list(network.subnets(new_prefix=new_prefix))
            return subnets[:int(num_subnets)] if num_subnets else subnets, None
        
        elif num_subnets:
            required_subnets = int(num_subnets)
            required_bits = 0
            while (2 ** required_bits) < required_subnets:
                required_bits += 1
            
            new_prefix = network.prefixlen + required_bits
            if new_prefix > 32:
                return None, "The requested number of subnets exceed the available address space."
            
            subnets = list(network.subnets(prefixlen_diff=required_bits))
            return subnets, None
        
        else:
            return list(network.subnets()), None
    except ValueError as e:
        return None, str(e)

def get_subnet_details(subnet):
    return {
        'network_address': str(subnet.network_address),
        'broadcast_address': str(subnet.broadcast_address),
        'netmask': str(subnet.netmask),
        'prefix_length': subnet.prefixlen,
        'num_addresses': subnet.num_addresses,
        'usable_hosts': subnet.num_addresses - 2 if subnet.num_addresses > 2 else 0,
        'first_host': str(subnet.network_address + 1) if subnet.num_addresses > 2 else "N/A",
        'last_host': str(subnet.broadcast_address - 1) if subnet.num_addresses > 2 else "N/A"
    }

@app.route('/', methods=['GET', 'POST'])
def index():
    subnet_info = None
    subnets = None
    error = None
    
    if request.method == 'POST':
        network_address = request.form['network_address']
        
        subnet_info, error = calculate_subnet_info(network_address)
        
        if subnet_info and not error:
            calculation_type = request.form.get('calculation_type')
            
            if calculation_type == 'num_subnets':
                num_subnets = request.form.get('num_subnets')
                if num_subnets:
                    subnet_list, subnet_error = calculate_subnets(network_address, num_subnets=num_subnets)
                    if subnet_error:
                        error = subnet_error
                    elif subnet_list:
                        subnets = [get_subnet_details(subnet) for subnet in subnet_list]
            
            elif calculation_type == 'hosts_per_subnet':
                hosts_per_subnet = request.form.get('hosts_per_subnet')
                num_subnets = request.form.get('num_subnets_for_hosts')
                if hosts_per_subnet:
                    subnet_list, subnet_error = calculate_subnets(
                        network_address, 
                        num_subnets=num_subnets,
                        hosts_per_subnet=hosts_per_subnet
                    )
                    if subnet_error:
                        error = subnet_error
                    elif subnet_list:
                        subnets = [get_subnet_details(subnet) for subnet in subnet_list]
    
    return render_template('index.html', subnet_info=subnet_info, subnets=subnets, error=error)

@app.route('/vlsm', methods=['GET', 'POST'])
def vlsm():
    subnet_info = None
    vlsm_subnets = None
    error = None
    
    if request.method == 'POST':
        network_address = request.form['network_address']
        
        subnet_info, error = calculate_subnet_info(network_address)
        
        if subnet_info and not error:
            try:
                num_subnets = int(request.form['num_vlsm_subnets'])
                hosts_requirements = []
                
                for i in range(1, num_subnets + 1):
                    hosts_field = f'subnet_{i}_hosts'
                    if hosts_field in request.form and request.form[hosts_field]:
                        hosts_requirements.append((i, int(request.form[hosts_field])))
                
                hosts_requirements.sort(key=lambda x: x[1], reverse=True)
                
                network = ipaddress.IPv4Network(network_address, strict=False)
                remaining_network = network
                vlsm_subnets = []
                
                for subnet_num, hosts in hosts_requirements:
                    required_bits = 0
                    while (2 ** required_bits - 2) < hosts:
                        required_bits += 1
                    
                    new_prefix = 32 - required_bits
                    
                    try:
                        subnet = next(remaining_network.subnets(new_prefix=new_prefix))
                        subnet_details = get_subnet_details(subnet)
                        subnet_details['subnet_number'] = subnet_num
                        subnet_details['required_hosts'] = hosts
                        vlsm_subnets.append(subnet_details)
                        
                        remaining_networks = list(remaining_network.address_exclude(subnet))
                        if remaining_networks:
                            remaining_network = remaining_networks[0]
                        else:
                            error = "Ran out of address space for subnet allocation"
                            break
                    except (StopIteration, ValueError):
                        error = f"Not enough address space for subnet {subnet_num} requiring {hosts} hosts"
                        break
                
            except ValueError as e:
                error = str(e)
    
    return render_template('vlsm.html', subnet_info=subnet_info, vlsm_subnets=vlsm_subnets, error=error)

if __name__ == '__main__':
    print(f"Looking for templates in: {template_dir}")
    app.run(debug=True)