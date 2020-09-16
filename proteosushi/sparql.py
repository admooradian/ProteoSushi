"""sparql.py: takes the results from proteoSushi and annotates it using the sparql API to access uniprot"""

__author__ = "Rob Seymour, Arshag Mooradian"
__email__ = "rseymour@wustl.edu"

from io import StringIO
import json

import csv
import pandas as pd
from re import findall
import requests
import sys  # Remove later
from time import sleep
import urllib


# Global constants
ENDPOINT = "https://sparql.uniprot.org"

def sparql_json_to_df(sparql_json_dict: dict):
    """Converts the messy json format into a dataframe

    Arguments:
        sparql_json_dict {dict} -- a json object retrieved through requests.get query
    Returns:
        sparql_df {pd.DataFrame} -- dataframe containing the results
    """
    
    cols = sparql_json_dict["head"]["vars"]

    temp_row_list = [] # list holding rows
    for row in sparql_json_dict["results"]["bindings"]:
        item = []
        for c in cols:
            item.append(row.get(c, {}).get("value"))
        temp_row_list.append(item)

    sparql_df = pd.DataFrame(temp_row_list, columns = cols)
    return sparql_df


def sparql_request(unpid_site_list: list, attempts_left=10):
    """Sends the request to uniprot to get data on each of the sites
    Arguments:
        unpidSiteList {list} -- a list of tuples with uniprot ID and site of PTM
    Returns:
    """
    unpid_site_list_str = ""
    if not unpid_site_list:
        return ""
    for tup in unpid_site_list:
        if len(tup) >= 2 and tup[1] == '0':
            tup[1] = '1'
        if len(tup[0]) >= 5:
            unpid_site_list_str += f"(uniprotkb:{tup[0]} {tup[1]})\n"
    # TODO: Delete this later
    #with open("sparqllist.tsv", 'w') as sparqllist:
    #    sparqllist.write(unpid_site_list_str)
    #print(unpid_site_list_str)

    query = """
PREFIX uniprotkb: <http://purl.uniprot.org/uniprot/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX faldo: <http://biohackathon.org/resource/faldo#>
PREFIX up: <http://purl.uniprot.org/core/>
PREFIX ec: <http://purl.uniprot.org/enzyme/>
 
SELECT
    ?entry
    #?annotation # I don't see any need for this actually
    ?lengthOfSequence #
    ?catalyicActivity #
    ?location #
    ?ec
    ?rhea
    ?type
    ?comment
    ?position ### New the position of the C that was given in the values
    ?begin #
    ?end #
    ?regionOfInterest ### subsequence of the annotation that had the C
FROM <http://sparql.uniprot.org/uniprot>
WHERE {
    VALUES (?entry ?position) {""" + unpid_site_list_str + """}
   ?entry up:sequence ?sequence .
   ?annotation up:range ?range ;
               a ?type .
    ?entry up:annotation ?caAnnotation .
    ?caAnnotation a up:Catalytic_Activity_Annotation .
    ?caAnnotation up:catalyticActivity ?ca .
    
    OPTIONAL {
    ?entry up:annotation ?subAnnotation .
    ?subAnnotation a up:Subcellular_Location_Annotation .
    ?subAnnotation up:locatedIn/up:cellularComponent ?location .
    }
 
    OPTIONAL {
    ?ca up:enzymeClass ?ec .
    }
    
    OPTIONAL {
    ?ca up:catalyzedReaction ?rhea
    }
 
    OPTIONAL {      #this breaks the query and also doesn't seem to add anything critical
         ?annotation rdfs:comment ?comment .
   }

   ?range faldo:begin
       [ faldo:position ?begin ; faldo:reference ?sequence ] ;
          faldo:end
       [ faldo:position ?end ; faldo:reference ?sequence ] .
   FILTER (?begin <= ?position && ?position <= ?end) # position must be in canonical sequence
 
 
   # get the IUPAC AAs associated with the identifier
   ?sequence rdf:value ?iupac .
 
   # get the AA subsequence of the annotation as a new variable
   BIND(SUBSTR(?iupac, ?begin, ?end - ?begin + 1) AS ?regionOfInterest)
 
   # get length
   ?sequence rdf:value ?iupac .
   BIND(strlen(?iupac) AS ?lengthOfSequence)
 
 
   #Order desc by entry and ascending by position afterwards
} ORDER BY DESC(?entry) ASC(?position)"""

    prefix="""PREFIX uniprotkb: <http://purl.uniprot.org/uniprot/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX faldo: <http://biohackathon.org/resource/faldo#>
PREFIX up: <http://purl.uniprot.org/core/>
PREFIX ec: <http://purl.uniprot.org/enzyme/>"""


    query_entry_length_position = prefix + """
SELECT
    ?entry
    ?position ### New the position of the C that was given in the values
    ?lengthOfSequence
    ?begin
    ?end
    ?regionOfInterest ### subsequence of the annotation that had the C
FROM <http://sparql.uniprot.org/uniprot>
WHERE {
    VALUES (?entry ?position) {""" + unpid_site_list_str + """
    }
    ?entry up:sequence ?sequence .
    ?annotation up:range ?range ;
               a ?type .
    ?range faldo:begin
        [ faldo:position ?begin ; faldo:reference ?sequence ] ;
            faldo:end
        [ faldo:position ?end ; faldo:reference ?sequence ] .
    FILTER (?begin <= ?position && ?position <= ?end)
    # get the IUPAC AAs associated with the identifier
    ?sequence rdf:value ?iupac .
    # get the AA subsequence of the annotation as a new variable
    BIND(SUBSTR(?iupac, ?begin, ?end - ?begin + 1) AS ?regionOfInterest)
    # get length
    ?sequence rdf:value ?iupac .
    BIND(strlen(?iupac) AS ?lengthOfSequence)
} ORDER BY DESC(?entry) ASC(?position)"""


    query_entry_subcellular = prefix + """
SELECT
    ?entry 
    ?location
FROM <http://sparql.uniprot.org/uniprot>
WHERE {
    VALUES (?entry ?position) {""" + unpid_site_list_str + """
    }
    ?entry up:annotation ?subAnnotation .
    ?subAnnotation a up:Subcellular_Location_Annotation .
    ?subAnnotation up:locatedIn/up:cellularComponent ?location .
} ORDER BY DESC(?entry)"""


    query_catalytic = prefix + """
SELECT
    ?entry
    ?position
    ?catalyicActivity
FROM <http://sparql.uniprot.org/uniprot>
WHERE {
    VALUES (?entry ?position) {""" + unpid_site_list_str + """
    }
   ?entry up:sequence ?sequence .
    ?entry up:annotation ?caAnnotation .
    ?caAnnotation a up:Catalytic_Activity_Annotation .
    ?caAnnotation up:catalyticActivity ?ca .
} ORDER BY DESC(?entry) ASC(?position)"""


    query_ec_rhea_type = prefix + """
SELECT
    ?entry
    ?position
    ?ec
    ?rhea
    ?type
    ?comment
FROM <http://sparql.uniprot.org/uniprot>
WHERE {
    VALUES (?entry ?position) {""" + unpid_site_list_str + """
    }

    OPTIONAL {
        ?ca up:enzymeClass ?ec .
    }

    OPTIONAL {
    ?ca up:catalyzedReaction ?rhea .
    }

    OPTIONAL {
        ?annotation rdfs:comment ?comment .
    }

#Order desc by entry and ascending by position afterwards
} ORDER BY DESC(?entry) ASC(?position)"""
    # Grabs the annotation by parts to maximize the amount we receive from the uniprot server
    region_annot = request_annot(query_entry_length_position)
    catalytic_annot = request_annot(query_catalytic)
    subcell_annot = request_annot(query_entry_subcellular)
    #extras_annot = request_annot(query_ec_rhea_type)
    # Full outer joins the annotations to preserve all info possible
    if region_annot is None:
        region_annot = pd.DataFrame(columns=["entry", " position", " lengthOfSequence", " begin", " end", " regionOfInterest"])
    if catalytic_annot is None:
        catalytic_annot = pd.DataFrame(columns=["entry", " position", " catalyticActivity"])
    if subcell_annot is None:
        subcell_annot = pd.DataFrame(columns=["entry", " location"])
    #if extras_annot is None:
    #   extras_annot = pd.DataFrame(columns=["entry", " position", " ec", " rhea", " type", " comment"])
    full_annot = region_annot
    full_annot.merge(catalytic_annot, how="outer", on=["entry", " position"])
    full_annot.merge(subcell_annot, how="outer", on=["entry"])
    #full_annot.merge(extras_annot, how="outer", on=["entry", " position"])
    
    
    return full_annot

def request_annot(query: str, attempts_left=10):
    """Sends the query to uniprot and checks the output

    Arguments:
        query {str} -- the query with the sites to annotate
        attempts_left {int} -- the number of requests that can be sent out
    Returns:
        pandas.dataframe -- the returned annotation
    """
    headers = {"user-agent": "rseymour@wustl.edu"}
    time_to_sleep = 3
    try:
        r = requests.post(ENDPOINT, data = {"format": "csv", "query": query}, headers = headers)
        if "<!DOCTYPE html SYSTEM \"about:legacy-compat\">" in r.text:  # This just means it returned a 500 error
            if attempts_left > 0:
                sleep(time_to_sleep)
                print("\033[93m {}\033[00m".format(f"Attempts used: {11 - attempts_left}"))
                return request_annot(query, attempts_left - 1)
            else:
                return None  # TODO: remove this once Uniprot fixes their stuff
                raise pd.errors.ParserError("Ran out of Uniprot accession attempts")
        csv_file = StringIO(r.text)
        sparql_from_csv_df = pd.read_csv(csv_file)
    except pd.errors.ParserError:
        if attempts_left > 0:
            sleep(time_to_sleep)
            print("\033[93m {}\033[00m".format(f"Attempts used: {11 - attempts_left}"))
            return request_annot(query, attempts_left - 1)
        else:
            return None  # TODO: remove this once Uniprot fixes their stuff
            raise pd.errors.ParserError("Ran out of Uniprot accession attempts")
    return sparql_from_csv_df

def process_sparql_output(output_str, sparql_dict: dict) -> list:
    """Process the output from uniprot to make it consistent with the rollup output

    Arguments:
        output_str {pandas.dataframe} -- the string output from uniprot, may have multiple
        sparql_dict {dict} -- the growing dictionary of uniprot annotations
    Returns:
        list -- a list of annotations with the data properly separated
    """

    def __parse_sparql_line(line: str) -> str:
        """changes the complicated uniprot annotation output into a cleaner line

        Arguments:
            line {str} -- a line from the output
        Returns:
            str -- a cleaned up version of that same line
        """
        #entry,lengthOfSequence,catalyicActivity,location,ec,rhea,type,comment,position,begin,end,regionOfInterest
        new_str = list()
        for chunk in line[1]:
            if isinstance(chunk, str) and "http://purl.uniprot.org/uniprot/" in chunk:
                new_str.append(chunk.replace("http://purl.uniprot.org/uniprot/", ""))
            elif isinstance(chunk, str) and "http://purl.uniprot.org/core/" in chunk:
                new_str.append(chunk.replace("http://purl.uniprot.org/core/", ""))
            elif isinstance(chunk, str) and "http://purl.uniprot.org/locations/" in chunk:
                new_chunk = chunk.replace("http://purl.uniprot.org/locations/", "")
                new_str.append(subcellular_location_dict[new_chunk.zfill(4)])  # Converts the number location to descriptor
            elif isinstance(chunk, str) and "http://purl.uniprot.org/enzyme/" in chunk:
                new_chunk = chunk.replace("http://purl.uniprot.org/enzyme/", "")
                new_str.append(ec_id_to_description_dict[new_chunk])
            elif isinstance(chunk, str) and "^^<http://www.w3.org/2001/XMLSchema#int>" in chunk:
                new_str.append(findall(r"(\d+?)\^", chunk)[0])
            else:
                new_str.append(str(chunk))
        return '\t'.join(new_str)

    output_list = list()
    comments_dict = dict()
    #sparql_dict = dict()  # This gets used by the main program to connect these annotations to the rest of the data.
    output_lines = output_str
    if len(output_lines) == 1 or (not isinstance(output_lines, str) and output_lines.empty):
        print("Failed to get annotations")
        return output_list, sparql_dict
    
    try:
        position_index = output_lines.columns.get_loc(" position")
    except (AttributeError, KeyError):
        print("Missing the Position column")
        return output_list, sparql_dict

    # get the subcellular location from UniProt
    def retrieve_uniprot_subcellular_location():
        '''Retrieve subcellular location information from UniProt directly'''
        r = requests.get('https://www.uniprot.org/locations/?format=tab')
        subcellular_location_df = pd.read_csv(StringIO(r.text), sep = '\t')  # TODO: potential ParserError
        subcellular_location_df["location_id_reformatted"] = (subcellular_location_df["Subcellular location ID"]
                                                             .str.split("-")
                                                             .str[1]
                                                             )
        return subcellular_location_df
    
    subcellular_location_df = retrieve_uniprot_subcellular_location()
    subcellular_location_dict = dict(subcellular_location_df[["location_id_reformatted", "Alias"]].values.tolist())

    # Fetches a file from expasy to deal with the 'ec' column
    try:
        r = urllib.request.urlopen("ftp://ftp.expasy.org/databases/enzyme/enzyme.dat", "enzyme.dat")
    except urllib.error.URLError:
        sleep(10)
        r = urllib.request.urlopen("ftp://ftp.expasy.org/databases/enzyme/enzyme.dat", "enzyme.dat")
    enzyme_dat_list = r.read().decode("utf-8").split('\n')

    # Turn enzyme.dat into a dictionary for mapping
    ec_id_to_description_dict = dict()
    for line_number, line in enumerate(enzyme_dat_list):
        if line.startswith("ID "):
            current_id = line[5:]
            current_description = enzyme_dat_list[line_number + 1][5:]
            ec_id_to_description_dict[current_id] = current_description

    #entry,lengthOfSequence,catalyicActivity,location,ec,rhea,type,comment,position,begin,end,regionOfInterest
    #header = output_lines.colnames()
    #print(output_lines.columns)
    
    #i = 1
    repeat_index = 2
    #while i < len(output_lines):
    for output_line in output_lines.iterrows():  # TODO: optimize by vectorizing
        output_line = __parse_sparql_line(output_line)
        #print(output_split)
        # This should only have 1 iteration and is used to properly split the csv type line
        for output_split in csv.reader([output_line], delimiter='\t', quotechar='"'):
            key = ','.join([*output_split[:repeat_index], output_split[position_index]])
            try:
                comments_dict[key] += output_split[repeat_index:position_index] + output_split[position_index + 1:]
            except KeyError:
                comments_dict[key] = output_split[repeat_index:position_index] + output_split[position_index + 1:]
        #i += 1
    
    for key in comments_dict:
        output_list.append(key + ',' + ','.join(comments_dict[key]))
        sparql_dict[ key.split(',')[0] + '|' + key.split(',')[2] ] = key.split(',') + comments_dict[key] #unpid, pos
    #print(f"sparql_dict has {sparql_dict}")
    return output_list, sparql_dict
#EOF