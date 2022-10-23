import sys, os, shutil

sys.dont_write_bytecode = True

def main(argv):
    os.system("python setup.py install --user")
    shutil.rmtree("rsxr.egg-info")
    shutil.rmtree("build")
    shutil.rmtree("dist")

if __name__ == "__main__":
    sys.exit(main(sys.argv))
