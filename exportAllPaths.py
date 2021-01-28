import xml.etree.ElementTree as ET
import os
import copy
import sys
import threading
import subprocess

sys.path.append('/usr/share/inkscape/extensions')
import inkex

# Enumerate all layers (groups) and then paths in those layers
GROUP_ELEMENT = '{http://www.w3.org/2000/svg}g'
LAYER_LABEL = '{http://www.inkscape.org/namespaces/inkscape}label'
PATH_ELEMENT = '{http://www.w3.org/2000/svg}path'
PATH_ID = 'id'

shouldPrint = False
def doPrint(string):
    if shouldPrint:
        print(string)

def exportAllPaths(outDirectory, excludePrefix, splitLayers, fitPageToContents, exportType, exportDpi, tree):
    root = tree.getroot()
    layersExcluded=[]
    layerPaths={}
    for layer in root.findall(GROUP_ELEMENT):
        layerLabel = layer.get(LAYER_LABEL)
        # Exclude any layers that start with the prefix
        if layerLabel.startswith(excludePrefix):
            layersExcluded.append(layerLabel)
            continue
        layerPaths[layerLabel] = []
        for path in layer.findall(PATH_ELEMENT):
            pathId = path.get(PATH_ID)
            layerPaths[layerLabel].append(pathId)

    doPrint("Layers excluded: " + str(layersExcluded))
    doPrint("Layers included: " + str(layerPaths))

    # Export each path in each layer not excluded
    subtaskThreads = []
    for layerLabel in layerPaths:
        for pathId in layerPaths[layerLabel]:
            outTree = copy.deepcopy(tree)
            outRoot = outTree.getroot()
            for outLayer in outRoot.findall(GROUP_ELEMENT):
                outLayerLabel = outLayer.get(LAYER_LABEL)
                # Remove all layers other than the one we want to export
                if outLayerLabel != layerLabel:
                    outRoot.remove(outLayer)
                    continue
                # Make sure the layer is set to display
                outStyle = outLayer.get('style')
                if type(outStyle) is str:
                    outStyle = outStyle.replace('display:none', 'display:inline')
                    outLayer.set('style', outStyle)
                # Only remove the other paths if we are exporting one path at a time
                if splitLayers:
                    # Remove all paths other than the one we want to export
                    for outPath in outLayer.findall(PATH_ELEMENT):
                        outPathId = outPath.get(PATH_ID)
                        if outPathId != pathId:
                            outLayer.remove(outPath)
            # Record the destination
            outFile = layerLabel
            if splitLayers:
                outFile += '_' + pathId
            outFile += '.' + exportType
            outPath = os.path.join(outDirectory, outFile)
            # Create the post process command
            command = [
                'inkscape',
                '--vacuum-defs',
                '--export-area-drawing' if fitPageToContents else '--export-area-page',
                '--export-dpi=' + str(exportDpi),
                '--export-type=' + exportType,
                '--export-filename=-', # Send output to stdout
                '--pipe' # Take input from stdin
            ]
            rootAsString = ET.tostring(outRoot)
            # In another thread, wait for the inkscape processing
            def runSubtask(outFile, outPath, command, rootAsString):
                result = subprocess.run(command, input=rootAsString,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)
                if result.returncode != 0:
                    doPrint("Could not post-process '" + outFile + "'")
                    doPrint(result.stderr)
                else:
                    doPrint("Finishing post-process '" + outFile + "'")
                    doPrint("Writing result to '" + outPath + "'")
                    # Export the copied svg
                    outStream = os.open(outPath, os.O_RDWR | os.O_CREAT)
                    os.write(outStream, result.stdout)
                    os.close(outStream)
            thread = threading.Thread(target=runSubtask, args=(outFile, outPath, command, rootAsString))
            thread.start()
            subtaskThreads.append(thread)
            # If exporting as a layer, rather than individual paths, go to next layer
            if not splitLayers:
                break

    for thread in subtaskThreads:
        thread.join()

class ExportAllPaths(inkex.Effect):
    def __init__(self):
        inkex.Effect.__init__(self)
        self.arg_parser.add_argument('-o', '--out-directory',
                                     type=str,
                                     dest='outDirectory',
                                     default='~/',
                                     help='Path to the output directory')
        self.arg_parser.add_argument('-e', '--exclude-prefix',
                                     type=str,
                                     dest='excludePrefix',
                                     default='-',
                                     help='Prefix of layers to not export')
        self.arg_parser.add_argument('-s', '--split-layers',
                                     type=inkex.Boolean,
                                     dest='splitLayers',
                                     default=True,
                                     help='Export paths one by one as files')
        self.arg_parser.add_argument('-p', '--fit-page-to-contents',
                                     type=inkex.Boolean,
                                     dest='fitPageToContents',
                                     default=True,
                                     help='Fit output to content bounds')
        self.arg_parser.add_argument('-f', '--export-type',
                                     type=str,
                                     dest='exportType',
                                     default='svg',
                                     help='Exported file type')
        self.arg_parser.add_argument('-d', '--export-dpi',
                                     type=int,
                                     dest='exportDpi',
                                     default=96,
                                     help='PNG rasterization DPI')

    def effect(self):
        outDirectory = self.options.outDirectory
        if '~' in outDirectory:
            outDirectory = outDirectory[outDirectory.find('~'):]
            outDirectory = os.path.expanduser(outDirectory)
        if not os.path.exists(outDirectory):
            os.makedirs(outDirectory)

        exportAllPaths(outDirectory,
                       self.options.excludePrefix,
                       self.options.splitLayers,
                       self.options.fitPageToContents,
                       self.options.exportType,
                       self.options.exportDpi,
                       self.document)

def doCommandLine():
    global shouldPrint
    shouldPrint = True

    # We at least need to know what svg we are splitting
    if len(sys.argv) < 2:
        doPrint("Usage: exportAllPaths.py <svg/toSplit.svg> [output/directory/] [excludePrefix] [fitPageToContents] [exportType] [exportDpi]")
        doPrint("If only one argument is given, the output directory will")
        doPrint("be a directory of the same name and parent directory as")
        doPrint("the input svg.")
        exit(1)

    # Get or default the output directory
    outDirectory = sys.argv[2] if len(sys.argv) >= 3 else os.path.splitext(sys.argv[1])[0]
    doPrint("Output directory: '" + outDirectory + "'")
    if not os.path.exists(outDirectory):
        os.makedirs(outDirectory)

    # Get or default the prefix by which to exclude layers
    excludePrefix = sys.argv[3] if len(sys.argv) >= 4 else "-"

    # Get or default the flag for splitting layers to their paths
    splitLayers = sys.argv[4].lower() == 'true' if len(sys.argv) >= 5 else True

    # Get or default the flag for fitting the page size to export contents
    fitPageToContents = sys.argv[5].lower() == 'true' if len(sys.argv) >= 6 else True

    # Get or default the type of image to which to export the svg
    exportType = sys.argv[6] if len(sys.argv) >= 7 else 'svg'

    # Get or default the DPI at which to export the svg
    try:
        exportDpi = int(sys.argv[7]) if len(sys.argv) >= 8 else 300
    except:
        return

    # Parse the input file
    tree = ET.parse(sys.argv[1])

    exportAllPaths(outDirectory, excludePrefix, splitLayers, fitPageToContents, exportType, exportDpi, tree)

if __name__ == '__main__':
    try:
        ExportAllPaths().run(output=False)
    except Exception as e:
        inkex.errormsg(str(e))
        doCommandLine()
