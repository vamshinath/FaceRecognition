import cv2,os,sys
import face_recognition
from pymongo import MongoClient
from bson.binary import Binary
import pickle,hashlib,string,random
import shutil
from datetime import datetime

client = MongoClient("localhost")["faces"]

baseFileDir = "/home/intel/Desktop/faceRecog/References"

onlyBaseScan = input("Base or reg (r/*)") != "r"

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



def addToBaseHelperSingleDir(dr,files):

    for fl in files:
        try:
            flHash = getHash(fl)
            alreadyHash = list(client[dr].find({"fileHash":flHash}))
            if alreadyHash:
                continue
            alreadyHash = list(client["hashs_DND"].find({"fileHash":flHash}))
            if alreadyHash:
                continue
            faces,facesLocs = getFaces(fl)
            if len(faces) > 1:
                print(fl," has more than 1 face...skip")
                client["hashs_DND"].insert_one({"fileHash":flHash})
                continue
            else:
                currenFace = faces[0]
                x1,y1,x2,y2 = facesLocs[0]
                facA = faceArea([(x1,0),(x1,y1),(x2,0),(x2,y2)])
                client[dr].insert_one({"fl":fl,"dateAdded":datetime.now(),"lastUpdated":datetime.now(),"fileHash":flHash,"faceArea":facA,"face":Binary(pickle.dumps(currenFace,protocol=2),subtype=128)})
                print(fl,facA)
        except Exception as e:
            print(e)



def getEligibleFiles():
    global onlyBaseScan    

    if onlyBaseScan:
        dirsToCreate = list(map(lambda x:x.split("_Base")[0],filter(lambda x:"_Base" in x,client.list_collection_names())))
        
    else:
        dirsToCreate = list(filter(lambda x:not "_Base" in x and not "DND" in x,client.list_collection_names()))


    #dirsToCreate = list(map(lambda x:x.split("_Base")[0],filter(lambda x:"_Base" in x,client.list_collection_names())))
    currentDirs = list(filter(lambda x:os.path.isdir(x),os.listdir()))

    dirsToCreate = list(filter(lambda x: x not in currentDirs,dirsToCreate))

    if dirsToCreate:
        for dr in dirsToCreate:
            os.mkdir(dr)
            currentDirs.append(dr)

    dirsToScan = []
    for dr in currentDirs:
        files = list(filter(lambda x:"image" == getFileType(x),os.listdir(dr)))
        if files:
            files = list(map(lambda x:os.path.abspath(os.path.join(dr,x)),files))
            dirsToScan.append([dr,files])

    dirsToScan = sorted(dirsToScan,key=lambda x:len(x[1]),reverse=True)

    return dirsToScan


def addToBase():
    global onlyBaseScan
    dirsToScan = getEligibleFiles()
    totalDirsCount = len(dirsToScan)
    ctr=1
    for drnm,files in dirsToScan:
        if onlyBaseScan:
            drnm = drnm+"_Base"
        print(ctr,"/",totalDirsCount," Scanning....",drnm,len(files))
        addToBaseHelperSingleDir(drnm,files)
        ctr+=1


def fileBasedRankHelper1(dr,files):

    finalData={}

    for fl in files:
        try:

            flHash = getHash(fl)
            alreadyHash = list(client[dr].find({"fileHash":flHash}))
            if alreadyHash:
                continue
            alreadyHash = list(client["hashs_DND"].find({"fileHash":flHash}))
            if alreadyHash:
                continue
            face,floc = getFaces(fl)

            if len(face) != 1:
                print(fl,"Failed...")
                continue

            for rec in client[dr].find():
                exface = pickle.loads(rec["face"])

                vals = face_recognition.face_distance(face,exface)
                if len(vals) == 0:
                    continue
                val = min(vals)
                existingScores = finalData.get(rec["fileHash"],[])
                existingScores.append(val)
                finalData[rec["fileHash"]] = existingScores
        except Exception as e:
            print(fl,str(e))
        
    for fileHash,scores in finalData.items():
        if len(scores) < 3:
            print("Changes Images",dr)
            sys.exit(1)
        score = min(scores)
        client[dr].update_one({"fileHash":fileHash},{"$set":{"accuracy":score,"lastUpdated":datetime.now()}})
        print(dr,score,fileHash)
        

def fileBasedRank():
    global onlyBaseScan
    dirsToScan = getEligibleFiles()
    totalDirsCount = len(dirsToScan)
    ctr=1
    for drnm,files in dirsToScan:
        if onlyBaseScan:
            drnm = drnm+"_Base"
        print(ctr,"/",totalDirsCount," Scanning....",drnm,len(files))
        fileBasedRankHelper1(drnm,files)
        addToBaseHelperSingleDir(drnm,files)
        ctr+=1
    
def any10BasedRank1(dr,faces):

    for rec in faces:
        try:
            exface = pickle.loads(rec["face"])
            fileHash = rec["fileHash"]
            for rec2 in client[dr].find():
                if rec2["fileHash"] == fileHash:
                    continue
                vals = face_recognition.face_distance([exface],pickle.loads(rec2["face"]))
                if len(vals) == 0:
                    continue
                val = min(vals)
                print(val)
                try:
                    existingAccuracy = rec["accuracy"]
                except Exception as e:
                    existingAccuracy = 100
                
                if existingAccuracy > val:
                    print("Updated")
                    client[dr].update_one({"fileHash":rec2["fileHash"]},{"$set":{"accuracy":val,"lastUpdated":datetime.now()}})
                    existingAccuracy = val

        except Exception as e:
            print(e)


def any10BasedRank():


    if onlyBaseScan:
        collections = list(filter(lambda x:"_Base" in x,client.list_collection_names()))
        
    else:
        collections = list(filter(lambda x:not "_Base" in x and not "DND" in x,client.list_collection_names()))



    toProcess = {}

    for ct in collections:
        print(ct)
        tmp = list(client[ct].find())
        toProcess[ct] = random.choices(tmp,k=10 if len(tmp)>10 else len(tmp))

    collectionToUpdate = input("Enter collection:")
    recs = []
    if collectionToUpdate:
        recs.append([collectionToUpdate,toProcess[collectionToUpdate]])
    else:
        for ctnm,faces in toProcess.items():
            recs.append([ctnm,faces])
    
    for dr,faces in recs:
        print(dr)
        any10BasedRank1(dr,faces)


def updateBaseScores():

    ch = input("Enter choice \n 1.FileBased 2.Any 10 Base:")
    
    if ch == "1":
        print("Files Based re-ranking......")
        fileBasedRank()
    elif ch == "2":
        print("Any 10 re-ranking.......")
        any10BasedRank()


def removeFromBase(score=0.3489):
    global onlyBaseScan

    if onlyBaseScan:
        collections = list(filter(lambda x:"_Base" in x,client.list_collection_names()))
        
    else:
        score = float(input("Enter 0.3489 score:"))
        collections = list(filter(lambda x:not "_Base" in x and not "DND" in x,client.list_collection_names()))


    for ct in collections:
        ctr=0
        for rec in client[ct].find():
            try:
                if rec["accuracy"] > score:
                    client[ct].delete_one({"_id":rec["_id"]})
                    ctr+=1
            except Exception as e:
                e=0
        print("Deleted ",ct,ctr)
            

def listRecs():

    global onlyBaseScan
    ch = input("Enter choice: \n 1.Top Accurate 2.Less Base 3. 3.More Base 4. Less Accurate")


    if onlyBaseScan:
        collections = list(filter(lambda x:"_Base" in x,client.list_collection_names()))
    else:
        collections = list(filter(lambda x: not "_Base" in x and not "DND" in x,client.list_collection_names()))

    
    data={}
    for ct in collections:
        mina=100
        maxa=0
        totalacc=0
        recs = list(client[ct].find())
        for rec in recs:
            try:
                acc = rec["accuracy"] 
                if acc > maxa:
                    maxa = acc
                if acc < mina:
                    mina = acc
                totalacc+=acc
            except Exception as e:
                print(e)
        data[ct] = [mina,maxa,totalacc/len(recs),len(recs)]
    
    if ch == "1":
        finalData = sorted(data.items(),key=lambda x:x[1][2],reverse=True)
    elif ch == "4":
        finalData = sorted(data.items(),key=lambda x:x[1][2],reverse=False)
    elif ch == "3":
        finalData = sorted(data.items(),key=lambda x:x[1][3],reverse=True)
    elif ch == "2":
        finalData = sorted(data.items(),key=lambda x:x[1][3],reverse=False)
    
    for dt in finalData:
        print(dt[0],dt[-1][-1])





def startHere():
    os.chdir(baseFileDir)
    user_choice = input("Enter your choice \n 1. Add to Base \n 2.Update Base Scores \n 3.Remove from Base \n 4.List Base \n:")

    if user_choice == "1":
        addToBase()
    elif user_choice == "2":
        updateBaseScores()
    elif user_choice == "3":
        removeFromBase(0.3489)
    else:
        listRecs()
    



if __name__ == "__main__":
    startHere()