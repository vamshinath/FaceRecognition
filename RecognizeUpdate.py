import cv2,os,sys
import face_recognition
from pymongo import MongoClient
from bson.binary import Binary
import pickle,hashlib,string,random
import shutil
from datetime import datetime

client = MongoClient("localhost")["faces"]

file_extensions={}

file_extensions["image"]=[
    "jpg","jpeg","png","webp"]
file_extensions["video"]=[
    "mp4",
    "mkv",
    "flv",
    "mpeg",
    "mov",
    "avi",
    "x-matroska",
    "x-m4v",
    "octet-stream",
    "m4v",
    "webm",
    "m2ts",
    "ts"
]

def faceArea(corners):
    n = len(corners) # of corners
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += corners[i][0] * corners[j][1]
        area -= corners[j][0] * corners[i][1]
    area = abs(area) / 2.0
    return area


def getHash(fl):
    BLOCKSIZE = 4096
    hasher = hashlib.md5()

    readBytes=0

    with open(fl, 'rb') as afile:
        buf = afile.read(BLOCKSIZE)
        while len(buf) > 0:
            hasher.update(buf)
            buf = afile.read(BLOCKSIZE)
            readBytes+=BLOCKSIZE
    
    file_hash = hasher.hexdigest()

    return file_hash

def getFaces(fl):
    try:
        image = face_recognition.load_image_file(fl)
        faces = face_recognition.face_encodings(image,num_jitters=50)
        floc = face_recognition.face_locations(image)
    except Exception as e:
        faces=floc=None    
    return [faces,floc]

def getFileType(fl):

    flext = fl.split(".")[-1]

    for extype,vals in file_extensions.items():
        if flext.lower() in vals:
            return extype
    
    if flext == "gif":
        return "gif"
    else:
        return "UN"



def guessName(face,collection=None,collectionPat=None):

    if collection:
        collections=[]
        collections.append(collection)
    else:
        collections = list(filter(lambda x:not "DND" in x,client.list_collection_names()))
    
    results=100
    actressNameFin=None

    for actress in collections:
        if collectionPat:
            if not collectionPat.lower() in actress.lower():
                continue
        faces = client[actress].find({})
        actressFaces = []
        for fc in faces:
            fc = pickle.loads(fc["face"])
            actressFaces.append(fc)
        try:
            vals = face_recognition.face_distance(actressFaces,face)
        except Exception as e:
            continue
        if len(vals) == 0:
            continue
        val = min(vals)
        if val < 0.459985:
            if results > val:
                results = val
                actressNameFin=actress
    
    if actressNameFin:
        return [actressNameFin,results]
        #return actress if face_recognition.compare_faces(actressFaces,face1,tolerance=0.05) else None
    return [None,None]



def get_random_alphanumeric_string(length=5):
    letters_and_digits = string.ascii_letters + string.digits+ string.ascii_lowercase
    result_str = ''.join((random.choice(letters_and_digits) for i in range(length)))

    return result_str


def guessName2(fl):
    print(fl)
    faces,flocs = getFaces(fl)
    largeFace = faceAreae=0
    for i,face in enumerate(faces):
        if len(face):
            floc = flocs[i]
            x1,y1,x2,y2 = floc
            facA = faceArea([(x1,0),(x1,y1),(x2,0),(x2,y2)])
            if facA > faceAreae:
                faceAreae = facA
                largeFace = face
    guessNamee,accuracy = guessName(largeFace,None,None)

    return guessNamee,accuracy



def main():

    passedDir = os.path.abspath(sys.argv[1])
    os.chdir(passedDir)
    pwd = os.getcwd()
    print("operating in :",pwd)
    input("Press Enter to continue")

    excollectionName = input("Enter exact collection Name:")
    collectionPatt = input("Enter collection Pattern:")

    files = list(filter(lambda x:"image" == getFileType(x) and not x.startswith("NoS") and not x.startswith("fr-") ,os.listdir()))

    for fl in files:
        print(fl)
        faces,flocs = getFaces(fl)
        largeFace = faceAreae=0
        for i,face in enumerate(faces):
            if len(face):
                floc = flocs[i]
                x1,y1,x2,y2 = floc
                facA = faceArea([(x1,0),(x1,y1),(x2,0),(x2,y2)])
                if facA > faceAreae:
                    faceAreae = facA
                    largeFace = face
        guessNamee,accuracy = guessName(largeFace,excollectionName,collectionPatt)
        if guessNamee:
            print("Guessed as ",guessNamee,accuracy,faceAreae)
            actressName = guessNamee.split("_Base")[0]

            if accuracy < 0.3489:
                client[actressName].insert_one({"fl":fl,"faceArea":faceAreae,"fileHash":getHash(fl),"actress":actressName,"isBase":"_Base" in guessNamee
                ,"accuracy":accuracy,"face":Binary(pickle.dumps(largeFace,protocol=2),subtype=128)})
                print(actressName,"updated")

            basefl = os.path.basename(fl)
            flext = basefl.split(".")[-1]
            dst_file = "fr-"+actressName+str(accuracy)[:4]+"_"+str(faceAreae)+"_"+get_random_alphanumeric_string()+"."+flext
            src_basepath = os.path.dirname(fl)
            new_fl = os.path.join(src_basepath,dst_file)
            shutil.move(fl,new_fl)
            print(new_fl,"\n")

        else:
            print("Failed","\n")


if __name__ == "__main__":
    main()
