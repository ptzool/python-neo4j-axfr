#!/usr/bin/python
import dns.resolver
import dns.query
import dns.zone
import os
import socket

from ipwhois import IPWhois
from multiprocessing import Pool
from py2neo import neo4j

DATAPATH = "zones"

class Neo4J:
  def __init__(self, dnsname, servername):
    self.graph = neo4j.Graph()
    self.dnsname = dnsname
    self.servername = servername

    self.add_node("DNS","name",dnsname)
    self.add_node("SERVER","name",servername)
    self.create_relations("DNS","name",dnsname,"SERVER","name",servername,"DNS")

    server_country_code = self.get_country_code(self.get_ip_from_hostname(servername))
    self.add_node("COUNTRY","name",server_country_code)

    dnsserver_country_code = self.get_country_code(self.get_ip_from_hostname(dnsname))
    self.add_node("COUNTRY","name",dnsserver_country_code)

    server_company_name = self.get_company(self.get_ip_from_hostname(servername))
    self.add_node("COMPANY","name",server_company_name)

    dnsserver_company_name = self.get_company(self.get_ip_from_hostname(dnsname))
    self.add_node("COMPANY","name",dnsserver_company_name)

    self.create_relations("SERVER","name",servername,"COMPANY","name",server_company_name,"HOSTED_BY")
    self.create_relations("DNS","name",dnsname,"COMPANY","name",dnsserver_company_name,"HOSTED_BY")
    self.create_relations("COMPANY","name",server_company_name,"COUNTRY","name",server_country_code,"FROM")
    self.create_relations("COMPANY","name",dnsserver_company_name,"COUNTRY","name",dnsserver_country_code,"FROM")

  def add_node(self, node_label, node_property_key, node_property_value):
    node = neo4j.Node(node_label, name=node_property_value)

    if not list(self.graph.find(node_label, property_key=node_property_key, property_value=node_property_value)):
      self.graph.create(node)

  def create_relations(self, slabel, sproperty_key, sproperty_value, elabel, eproperty_key, eproperty_value, relation_label):
    start_node = self.graph.find_one(slabel, property_key=sproperty_key, property_value=sproperty_value)
    end_node = self.graph.find_one(elabel, property_key=eproperty_key, property_value=eproperty_value)

    self.create_relation_if_not_exists(start_node, end_node, relation_label)

  def get_ip_from_hostname(self, hostname):
    return socket.gethostbyname(hostname)

  def get_country_code(self, ipv4):
    obj = IPWhois(ipv4)
    results = obj.lookup()

    return results['nets'][0]['country']

  def get_company(self, ipv4):
    obj = IPWhois(ipv4)
    results = obj.lookup()

    return results['nets'][0]['description']

  def create_relation_if_not_exists(self, start_node, end_node, relationship):
    if len(list(self.graph.match(start_node=start_node, end_node=end_node, rel_type=relationship))) > 0:
      return false
    else:
      relation = neo4j.Relationship(start_node, relationship, end_node)
      self.graph.create(relation)

def checkaxfr(domain):
  domain = domain.strip()
  try:
    ns_query = dns.resolver.query(domain,'NS')
    for ns in ns_query.rrset:
      nameserver = str(ns)[:-1]
      if nameserver is None or nameserver == "":
        continue

      if os.path.exists("." + os.sep + DATAPATH + os.sep + domain + "#" + nameserver + ".zone"):
        continue

      try:
        axfr = dns.query.xfr(nameserver, domain, lifetime=5)
        try:
          zone = dns.zone.from_xfr(axfr)
          if zone is None:
            continue
          fHandle = open("." + os.sep + DATAPATH + os.sep + domain + "#" + nameserver + ".zone", "w")
          print("Success: " + domain + " @ " + nameserver)

          Neo4J(nameserver, domain)

          for name, node in zone.nodes.items():
            rdatasets = node.rdatasets
            for rdataset in rdatasets:
              fHandle.write(str(name) + " " + str(rdataset) + "\n")
          fHandle.close()
        except Exception as e:
          continue
      except Exception as e:
        continue
  except Exception as e:
    pass
  print("Finished: " + domain)

def main():
  pool = Pool(processes=20)
  lines = open("domains.txt", "r").readlines()
  pool.map(checkaxfr, lines)
if __name__ == '__main__':
  main()
