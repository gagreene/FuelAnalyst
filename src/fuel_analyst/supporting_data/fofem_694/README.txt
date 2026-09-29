runfofem is the command line version of multiplatform FOFEM

Product of the Missoula Fire Sciences Laboratory

Attribution: Any use of the data derived from runfofem requires the following citation:

"Fire Effects calculations produced with the command line applications developed by the Missoula Fire Sciences Laboratory, Missoula, MT"

Sample data is included with this distribution
In order to successfully run the sample data, open a command prompt, navigate to the runfofem directory, and run the SetENV.bat file to correctly set the environment

e.g.
C:\runfofem>SetENV

Then navigate to the runfofem\share\sampledata directory:
C:\runfofem>cd sampledata

C:\runfofem\sampledata>testConsume
C:\runfofem\sampledata>testSoil
C:\runfofem\sampledata>testMort
C:\runfofem\sampledata>testMortSalvage

All outputs will be written to the C:\runfofem\sampledata\out directory.

Note that SetENV.bat is only valid for the current command prompt session.
In order to make these settings permanent you must add runfofem\bin to your PATH environment variable, and you must set the FOFEM_DATA environment variable to runfofem\share\fofem
Note that the above must include complete drive and path information.

e.g.
If runfofem is extracted to C:\runfofem, PATH must include "C:\runfofem\bin", and FOFEM_DATA must be set to "C:\runfofem\share\fofem"
