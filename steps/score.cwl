#!/usr/bin/env cwl-runner

cwlVersion: v1.0
class: CommandLineTool
label: Score predictions file
baseCommand: python3

hints:
  DockerRequirement:
    dockerPull: sagebionetworks/synapsepythonclient:v2.3.0

requirements:
  - class: InlineJavascriptRequirement
  - class: InitialWorkDirRequirement
    listing:
      - $(inputs.score_script)

inputs:
  - id: evaluation_id
    type: string
  - id: input_file
    type: File?
  - id: goldstandard_path
    type: string
  - id: check_validation_finished
    type: boolean?

arguments:
  - valueFrom: $(inputs.score_script.path)
  - prefix: -e
    valueFrom: $(inputs.evaluation_id)
  - prefix: -g
    valueFrom: $(inputs.goldstandard_path)
  - prefix: -i
    valueFrom: $(inputs.input_file)
  - prefix: -r
    valueFrom: results.json

outputs:
  - id: results
    type: File
    outputBinding:
      glob: results.json