from fhir_converter.renderers import Hl7v2Renderer

import hl7
import os

HL7V2_DIR = "data/sample/hl7v2"

with open("data/sample/hl7v2/ADT-A01-02.hl7",mode="r",encoding="utf-8") as hl7v2_in:
    result = Hl7v2Renderer().render_fhir_string("ADT_A01", hl7v2_in)
    print(result)

files_to_transform = []
passed_files = []
failed_files = []
for filename in os.listdir(HL7V2_DIR):
    if filename.endswith(".hl7"):
        with open(f"{HL7V2_DIR}/{filename}",mode="r",encoding="utf-8") as hl7v2_in:
            hl7v2_str = hl7v2_in.read().replace("\n","\r")
            file = {}
            try:
                hl7v2_msg = hl7.parse(hl7v2_str)
                file["filename"] = filename
                try:
                    file["message_type"] = str(hl7v2_msg.segment("MSH")[9][0][2])
                except IndexError:
                    try:
                        file["message_type"] = str(hl7v2_msg.segment("MSH")[9][0][0])+"_"+str(hl7v2_msg.segment("MSH")[9][0][1])
                    except IndexError:
                        file["message_type"] = str(hl7v2_msg.segment("MSH")[9][0])
            except Exception as e:
                print(f"Error parsing {filename}")
                failed_files.append({"filename":filename,"error":str(e)})
                continue
            files_to_transform.append(file)

for file in files_to_transform:
    with open(f"{HL7V2_DIR}/{file['filename']}",mode="r",encoding="utf-8") as hl7v2_in:
        try:
            result = Hl7v2Renderer().render_fhir_string(file["message_type"], hl7v2_in)
            passed_files.append({"filename":file["filename"],"result":result})
        except Exception as e:
            print(f"Error rendering {file['filename']}")
            failed_files.append({"filename":file["filename"],"error":str(e)})
            continue

# write results to files in data/results/{filename}.json
import json
for file in passed_files:
    with open(f"data/results/passed/{file['filename']}.json",mode="w",encoding="utf-8") as result_file:
        result_file.write(json.dumps(file["result"],indent=2))

for file in failed_files:
    with open(f"data/results/error/{file['filename']}.json",mode="w",encoding="utf-8") as result_file:
        result_file.write(json.dumps({"error":file["error"]},indent=2))