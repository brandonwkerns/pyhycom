"""
pyhycom.py

A Python interface to HYCOM files.
"""
import numpy as np
import gzip
import os

def open_a_file(filename, mode):
    """
    Open the file using gzip if if is a gzipped file (ending in .gz),
    otherwise, use regular Python read.
    """
    if filename[-3:] == '.gz':
        file = gzip.open(filename, mode=mode)
    else:
        file = open(filename[:-1]+'a',mode=mode)
    return file


def get_b_filename(filename):
    """
    Return the name of the corresponding HYCOM "b" file.
    If it is a gzipped file, replace the .a.gz with .b,
    otherwise, replace .a with .b.
    """
    if filename[-3:] == '.gz':
        bfilename = filename[:-4] + 'b'
    else:
        bfilename = filename[:-1]+'b'
    return bfilename


def thickness2depths(dz):
    """
    Convert layer thickness values to depths.
    return tuple of (z_bottom, z_center, z_top) of each layer.
    """
    z_bottom = 0.0 * dz
    z_center = 0.0 * dz
    z_top = 0.0 * dz
    kdm, jdm, idm = dz.shape

    for k in range(1, kdm):
        z_top[k,:,:] = z_top[k-1,:,:] + dz[k-1,:,:]

    z_bottom[0:kdm-1,:,:] = z_top[1:kdm,:,:]
    z_bottom[kdm-1,:,:] = z_bottom[kdm-2,:,:] + dz[k,:,:]

    z_center = 0.5 * (z_top + z_bottom)

    return (z_bottom, z_center, z_top)


def getTextFile(filename):
    """
    Returns a list where each element contains text from each line
    of given text file.
    """
    return [line.rstrip() for line in open(filename,'r').readlines()]


def getDims(filename):
    """
    Returns HYCOM domain dimensions for a given
    archive or regional.grid .a file.
    NOTE: This does NOT work for regional.depth files.
    """
    f = getTextFile(get_b_filename(filename))
    #
    idmFound = False
    jdmFound = False
    for line in f:
        if 'idm' in line:
            idm = int(line.split()[0])
            idmFound = True
        if 'jdm' in line:
            jdm = int(line.split()[0])
            jdmFound = True
        if idmFound and jdmFound:break
    #
    if 'arch' in filename:
        kdm = int(f[-1].split()[4])
        return (kdm,jdm,idm)
    else:
        return (jdm,idm)


def getFieldIndex(field,filename):
    """
    Function description
    """
    f = getTextFile(get_b_filename(filename))
    if 'arch' in filename:f = f[10:]
    if 'grid' in filename:f = f[3:]
    if 'restart' in filename:f = f[2:]
    fieldIndex = []
    for line in f:
        if field == line.split()[0].replace('.','').replace(':',''):
            fieldIndex.append(f.index(line))
    return fieldIndex


def getNumberOfRecords(filename):
    """
    Function description
    """
    f = getTextFile(get_b_filename(filename))
    if 'arch' in filename:
        f = f[10:]; return len(f)
    if 'grid' in filename:
        f = f[3:]; return len(f)
    if 'depth' in filename:
        return 1
    if 'restart' in filename:
        f = f[2:]; return len(f)



def getBathymetry(filename,undef=np.nan):
    """
    Reads a HYCOM bathymetry file (e.g., regional.depth.a)
    and return the bathymetry field.
    Will get dims from regional.grid.a.
    """
    import numpy as np
    if os.path.dirname(filename) == '':
        jdm,idm = getDims('regional.grid.b')
    else:
        jdm,idm = getDims(os.path.dirname(filename)+'/regional.grid.a')
    file = open_a_file(filename, mode='rb')
    ## The data are stored as float32, which has 4 bytes per each value.
    data = file.read(idm*jdm*4)
    field = np.reshape(np.frombuffer(data,dtype='float32',count=idm*jdm).byteswap(),(jdm,idm))
    file.close()
    field[field>2**99] = undef
    return field


def getField(field,filename,undef=np.nan,layers=None,x_range=None,y_range=None):
    """
    A function to read hycom raw binary files (regional.grid.a, archv.*.a and forcing.*.a supported),
    and interpret them as numpy arrays.

    ## BK added layers option to get a set of specified layers instead of the full file.
    ## layers is zero based. Leave it as None (or set it to []) to get all layers.

    ## TODO: Have x_range, and y_range only access the needed data.
             Right now, it will read the entire domain then subset it.
             (For layers, it will skip over the layers not specified).
    """
    import numpy as np
    from os.path import getsize

    # Get domain dimensions:
    dims = getDims(filename)

    if dims.__len__() == 3:
        kdm = dims[0]
        jdm = dims[1]
        idm = dims[2]
    if dims.__len__() == 2:
        kdm = 0
        jdm = dims[0]
        idm = dims[1]

    reclen = 4*idm*jdm                                   # Record length in bytes
    ## HYCOM binary data is written out in chunks/"words" of multiples of 4096*4 bytes.
    ## In general, the length of one level of one variable (reclen) will fall between
    ## consecutive multiples of the wordlen. The data is padded to bring the volume
    ## up to the next multiple. The "pad" value below is how many bytes are needed to do this.
    wordlen = 4096*4
    pad = wordlen * np.ceil(reclen / wordlen) - reclen   # Pad size in bytes
    fieldRecords = getFieldIndex(field,filename)         # Get field record indices
    fieldAddresses = np.array(fieldRecords)*(reclen+pad) # Address in bytes

    file = open_a_file(filename,mode='rb') # Open file

    # Read field records:
    if fieldAddresses.size == kdm: # 3-d field
        field = np.zeros((kdm,jdm,idm))
        if layers is None:
            layers = []

        ## Figure out how many layers I need to read from the file.
        if len(layers) > 0:
            kmax = max(np.max(layers),kdm-1)
        else:
            kmax = kdm

        ## Read through layers sequentially.
        for k in range(kmax):
            file.seek(int(fieldAddresses[k]),0) # Move to address
            if len(layers) < 1:
                data = file.read(idm*jdm*4)
                field[k,:,:] = np.reshape(np.frombuffer(data,dtype='float32',count=idm*jdm),(jdm,idm)).byteswap()
            else:
                if k in layers:   ## Levels are 1 to kdm. Python indices are zero based.
                    data = file.read(idm*jdm*4)
                    field[k,:,:] = np.reshape(np.frombuffer(data,dtype='float32',count=idm*jdm),(jdm,idm)).byteswap()

        ## Keep only tha layers that were specified. (The others would be all zeros.)
        if len(layers) > 0:
            field = field[layers,:,:]

        if not x_range is None:
            field = field[:,:,x_range]

        if not y_range is None:
            field = field[:,y_range,:]

    else: # 2-d field
        file.seek(int(fieldAddresses[0]),0)     # Move to address
        data = file.read(idm*jdm*4)
        field = np.reshape(np.frombuffer(data,dtype='float32',count=idm*jdm),(jdm,idm)).byteswap()

        if not x_range is None:
            field = field[:,x_range]

        if not y_range is None:
            field = field[y_range,:]


    #field = field.byteswap() # Convert to little-endian

    file.close()
    field[field == np.float32(2**100)] = undef

    return field





def getFieldRestart(field,filename,dims,undef=np.nan,layers=None,x_range=None,y_range=None):
    """
    A function to read hycom raw binary files (regional.grid.a, archv.*.a and forcing.*.a supported),
    and interpret them as numpy arrays.

    ## BK added layers option to get a set of specified layers instead of the full file.
    ## layers is zero based. Leave it as None (or set it to []) to get all layers.

    ## TODO: Have x_range, and y_range only access the needed data.
             Right now, it will read the entire domain then subset it.
             (For layers, it will skip over the layers not specified).
    """
    import numpy as np
    from os.path import getsize

    kdm = dims[2]
    jdm = dims[0]
    idm = dims[1]

    reclen = 4*idm*jdm                                   # Record length in bytes
    ## HYCOM binary data is written out in chunks/"words" of multiples of 4096*4 bytes.
    ## In general, the length of one level of one variable (reclen) will fall between
    ## consecutive multiples of the wordlen. The data is padded to bring the volume
    ## up to the next multiple. The "pad" value below is how many bytes are needed to do this.
    wordlen = 4096*4
    pad = wordlen * np.ceil(reclen / wordlen) - reclen   # Pad size in bytes
    fieldRecords = getFieldIndex(field,filename)         # Get field record indices
    fieldAddresses = np.array(fieldRecords)*(reclen+pad) # Address in bytes

    file = open_a_file(filename,mode='rb') # Open file

    # Read field records:
    if fieldAddresses.size >= kdm: # 3-d field
        field = np.zeros((kdm,jdm,idm))
        if layers is None:
            layers = []

        ## Figure out how many layers I need to read from the file.
        if len(layers) > 0:
            kmax = max(np.max(layers),kdm-1)
        else:
            kmax = kdm

        ## Read through layers sequentially.
        for k in range(kmax):
            file.seek(int(fieldAddresses[k]),0) # Move to address
            if len(layers) < 1:
                data = file.read(idm*jdm*4)
                field[k,:,:] = np.reshape(np.frombuffer(data,dtype='float32',count=idm*jdm),(jdm,idm)).byteswap()
            else:
                if k in layers:   ## Levels are 1 to kdm. Python indices are zero based.
                    data = file.read(idm*jdm*4)
                    field[k,:,:] = np.reshape(np.frombuffer(data,dtype='float32',count=idm*jdm),(jdm,idm)).byteswap()

        ## Keep only tha layers that were specified. (The others would be all zeros.)
        if len(layers) > 0:
            field = field[layers,:,:]

        if not x_range is None:
            field = field[:,:,x_range]

        if not y_range is None:
            field = field[:,y_range,:]

    else: # 2-d field
        file.seek(int(fieldAddresses[0]),0)     # Move to address
        data = file.read(idm*jdm*4)
        field = np.reshape(np.frombuffer(data,dtype='float32',count=idm*jdm),(jdm,idm)).byteswap()

        if not x_range is None:
            field = field[:,x_range]

        if not y_range is None:
            field = field[y_range,:]


    #field = field.byteswap() # Convert to little-endian

    file.close()
    field[field == np.float32(2**100)] = undef

    return field







def getRecord(filename,dims,record,undef=np.nan):
    """
    A function to read hycom raw binary files (regional.grid.a, archv.*.a and forcing.*.a supported),
    and interpret them as numpy arrays.

    ## BK added layers option to get a set of specified layers instead of the full file.
    ## layers is zero based. Leave it as None (or set it to []) to get all layers.

    ## TODO: Have x_range, and y_range only access the needed data.
             Right now, it will read the entire domain then subset it.
             (For layers, it will skip over the layers not specified).
    """
    import numpy as np
    from os.path import getsize

    # Get domain dimensions:
    # dims = getDims(filename)
    #
    # if dims.__len__() == 3:
    #     kdm = dims[0]
    #     jdm = dims[1]
    #     idm = dims[2]
    # if dims.__len__() == 2:
    kdm = 0
    jdm = dims[0]
    idm = dims[1]

    reclen = 4*idm*jdm                                   # Record length in bytes
    ## HYCOM binary data is written out in chunks/"words" of multiples of 4096*4 bytes.
    ## In general, the length of one level of one variable (reclen) will fall between
    ## consecutive multiples of the wordlen. The data is padded to bring the volume
    ## up to the next multiple. The "pad" value below is how many bytes are needed to do this.
    wordlen = 4096*4
    pad = wordlen * np.ceil(reclen / wordlen) - reclen   # Pad size in bytes
    #fieldRecords = getFieldIndex(field,filename)         # Get field record indices
    fieldAddress = np.array(record)*(reclen+pad) # Address in bytes

    file = open_a_file(filename,mode='rb') # Open file

    file.seek(int(fieldAddress),0)     # Move to address
    data = file.read(idm*jdm*4)
    field = np.reshape(np.frombuffer(data,dtype='float32',count=idm*jdm),(jdm,idm)).byteswap()

    #field = field.byteswap() # Convert to little-endian

    file.close()
    field[field == np.float32(2**100)] = undef

    return field








def get_vertical_profiles_at_points(field_list,filename,points,undef=np.nan):
    """
    F = get_vertical_profiles_at_points(field_list,filename,points,undef=np.nan)

    field_list is a list of field names to get. Alternatively, a string with a single field name.
    filename is the .a file.
    points is a 2D array or list of lists, with each row being a lon and lat.
    It can be just [lon,lat] to get a single profile.

    The script uses nearest neighbor interpolation. This avoids having to deal
    with different vertical coordinates at adjacent points.

    The function will return a dict containing 2D arrays for each variable.
    """

    from scipy.interpolate import NearestNDInterpolator

    ## Handle field_list if it is just a string of a single field.
    if not type(field_list) is list:
        field_list = [field_list]
    field_list = ['thknss'] + field_list

    ## Handle points if only one point specified.
    if not type(points[0]) is list:
        points = [points]
    points = np.array(points)

    ## Get regional.grid.a file.
    gridfilename = os.path.dirname(filename) + '/regional.grid.a'

    ## Get lat/lon and bounds for the points.
    min_lon = np.min(points[:,0])
    max_lon = np.max(points[:,0])
    min_lat = np.min(points[:,1])
    max_lat = np.max(points[:,1])
    lon = getField('plon', gridfilename, np.nan)
    lat = getField('plat', gridfilename, np.nan)

    ## Add buffer region of 1 deg, in case all the points specified are too close together
    ## in which case, x_range and/or y_range may end up empty below.
    x_range = [x for x in range(lon.shape[1]) if np.min(lon[:,x]) > min_lon-1.01 and np.max(lon[:,x]) < max_lon+1.01]
    y_range = [x for x in range(lat.shape[0]) if np.min(lat[x,:]) > min_lat-1.01 and np.max(lat[x,:]) < max_lat+1.01]
    lon = lon[y_range,:][:,x_range]
    lat = lat[y_range,:][:,x_range]

    ## Process each field.
    field_profile_list = []
    for field_name in field_list:
        field_data = getField(field_name, filename, undef=undef, layers=None
                    , x_range = x_range, y_range = y_range)

        field_profile = np.zeros([field_data.shape[0],points.shape[0]])

        for kk in range(field_data.shape[0]):
            interp = NearestNDInterpolator((lon.flatten(),lat.flatten()),field_data[kk,:,:].flatten())
            field_profile[kk,:] = interp(points) #[points[:,0],points[:,1]])

        field_profile_list += [field_profile]

    ## Get depth from thickness.
    field_profile_list[0] /= 9806.0

    depth_bottom = 1.0*field_profile_list[0] #/ 9806.0
    for k in range(1, field_data.shape[0]):
        depth_bottom[k,:] = depth_bottom[k-1,:] + depth_bottom[k,:]

    depth = 0.0*depth_bottom
    depth[0,:] = depth_bottom[0,:] / 2.0
    for k in range(1, field_data.shape[0]):
        depth[k,:] = 0.5*(depth_bottom[k-1,:] + depth_bottom[k,:])

    FOUT={}
    FOUT['depth_bottom_of_layer'] = depth_bottom
    FOUT['depth_middle_of_layer'] = depth
    FOUT['lon'] = 0.0*depth
    FOUT['lat'] = 0.0*depth
    for k in range(field_data.shape[0]):
        FOUT['lon'][k,:] = points[:,0]
        FOUT['lat'][k,:] = points[:,1]

    for ii in range(len(field_list)):
        FOUT[field_list[ii]] = field_profile_list[ii]

    return FOUT




def get_vertical_profiles(field_list,dir,trajectory,undef=np.nan, nz=41, atm_fields=None):
    """
    F = get_vertical_profiles(field_list,dir,trajectory,undef=np.nan)

    field_list is a list of field names to get. Alternatively, a string with a single field name.
    filename is the .a file.

    A trajectory dictionary has keys 'datetime','lon','lat'

    nz is the number of layers to get.

    The script uses nearest neighbor interpolation. This avoids having to deal
    with different vertical coordinates at adjacent points.

    The function will return a dict containing 2D arrays for each variable.
    """

    import glob
    from scipy.interpolate import NearestNDInterpolator

    ## Handle field_list if it is just a string of a single field.
    if not type(field_list) is list:
        field_list = [field_list]
    field_list = ['thknss'] + field_list

    ## Handle points if only one point specified.
    points = np.array([trajectory['lon'].tolist(),trajectory['lat'].tolist()]).T

    ## Get regional.grid.a file.
    gridfilename = (dir + '/regional.grid.a')

    ## Get lat/lon and bounds for the points.
    min_lon = np.min(points[:,0])
    max_lon = np.max(points[:,0])
    min_lat = np.min(points[:,1])
    max_lat = np.max(points[:,1])
    lon = getField('plon', gridfilename, np.nan)
    lat = getField('plat', gridfilename, np.nan)

    ## Add buffer region of 1 deg, in case all the points specified are too close together
    ## in which case, x_range and/or y_range may end up empty below.
    x_range = [x for x in range(lon.shape[1]) if np.min(lon[:,x]) > min_lon-1.01 and np.max(lon[:,x]) < max_lon+1.01]
    y_range = [x for x in range(lat.shape[0]) if np.min(lat[x,:]) > min_lat-1.01 and np.max(lat[x,:]) < max_lat+1.01]
    lon = lon[y_range,:][:,x_range]
    lat = lat[y_range,:][:,x_range]


    ## Initialize fields.
    field_profile_list = []
    for field_name in field_list:
        field_profile = np.zeros([nz,points.shape[0]])
        field_profile_list += [field_profile]


    ## Process each field at each time.
    for tt in range(len(trajectory['datetime'])):
        filename = glob.glob(trajectory['datetime'][tt].strftime(dir + '/archv.%Y_%j_%H.a*'))[0]
        print(filename)

        ffff=-1
        for field_name in field_list:
            ffff+=1
            field_data = getField(field_name, filename, undef=undef, layers=None
                        , x_range = x_range, y_range = y_range)

            for kk in range(nz):
                interp = NearestNDInterpolator((lon.flatten(),lat.flatten()),field_data[kk,:,:].flatten())
                field_profile_list[ffff][kk,tt] = interp(points[tt,:]) #[points[:,0],points[:,1]])

    ## Get depth from thickness.
    field_profile_list[0] /= 9806.0

    depth_bottom = 1.0*field_profile_list[0] #/ 9806.0
    for k in range(1, field_data.shape[0]):
        depth_bottom[k,:] = depth_bottom[k-1,:] + depth_bottom[k,:]

    depth = 0.0*depth_bottom
    depth[0,:] = depth_bottom[0,:] / 2.0
    for k in range(1, field_data.shape[0]):
        depth[k,:] = 0.5*(depth_bottom[k-1,:] + depth_bottom[k,:])

    FOUT={}
    FOUT['depth_bottom_of_layer'] = depth_bottom
    FOUT['depth_middle_of_layer'] = depth
    FOUT['lon'] = 0.0*depth
    FOUT['lat'] = 0.0*depth
    for k in range(field_data.shape[0]):
        FOUT['lon'][k,:] = points[:,0]
        FOUT['lat'][k,:] = points[:,1]

    for ii in range(len(field_list)):
        FOUT[field_list[ii]] = field_profile_list[ii]

    return FOUT


def get_wrf_surface_transect(field_list,dir,trajectory,undef=np.nan, DOM='d01'):

    """
    F = get_wrf_surface_transect(field_list,dir,trajectory,undef=np.nan)

    field_list is a list of field names to get. Alternatively, a string with a single field name.
    filename is the .a file.

    A trajectory dictionary has keys 'datetime','lon','lat'

    The script uses nearest neighbor interpolation. This avoids having to deal
    with different vertical coordinates at adjacent points.

    The function will return a dict containing 1D arrays for each variable.
    """

    from netCDF4 import Dataset
    from scipy.interpolate import NearestNDInterpolator

    ## Handle field_list if it is just a string of a single field.
    if not type(field_list) is list:
        field_list = [field_list]

    ## Handle points if only one point specified.
    points = np.array([trajectory['lon'].tolist(),trajectory['lat'].tolist()]).T


    ## Get lat/lon and bounds for the points.
    min_lon = np.min(points[:,0])
    max_lon = np.max(points[:,0])
    min_lat = np.min(points[:,1])
    max_lat = np.max(points[:,1])


    ## Initialize fields.
    field_transect_list = []
    for field_name in field_list:
        field_transect = np.zeros(points.shape[0])
        field_transect_list += [field_transect]


    ## Process each field at each time.
    for tt in range(len(trajectory['datetime'])):
        filename = trajectory['datetime'][tt].strftime(dir + '/wrfout_'+DOM+'_%Y-%m-%d_%H:00:00')
        print(filename)

        DS=Dataset(filename)
        lon = DS['XLONG'][:]
        lat = DS['XLAT'][:]

        ## Add buffer region of 1 deg, in case all the points specified are too close together
        ## in which case, x_range and/or y_range may end up empty below.
        #x_range = [x for x in range(lon.shape[1]) if np.min(lon[:,x]) > min_lon-1.01 and np.max(lon[:,x]) < max_lon+1.01]
        #y_range = [x for x in range(lat.shape[0]) if np.min(lat[x,:]) > min_lat-1.01 and np.max(lat[x,:]) < max_lat+1.01]
        #lon = lon[y_range,:][:,x_range]
        #lat = lat[y_range,:][:,x_range]

        ffff=-1
        for field_name in field_list:
            ffff+=1
            field_data = DS[field_name][:]

            interp = NearestNDInterpolator((lon.flatten(),lat.flatten()),field_data[0,:,:].flatten())
            field_transect_list[ffff][tt] = interp(points[tt]) #[points[:,0],points[:,1]])
        DS.close()

    FOUT={}
    FOUT['lon'] = 0.0*field_transect_list[0]
    FOUT['lat'] = 0.0*field_transect_list[0]
    FOUT['lon'] = points[:,0]
    FOUT['lat'] = points[:,1]

    for ii in range(len(field_list)):
        FOUT[field_list[ii]] = field_transect_list[ii]

    return FOUT



#
########################################################################
#
def ab2nc(filename):
    #
    """
    A function that converts a given hycom binary .a file into an equivalent .nc file.

    Module requirements: numpy,netCDF4,matplotlib.dates

    THIS FUNCTION DOES NOT YET WORK FOR FORCIGN FILES. TODO: Fix forcing files portion.
    """
    #
    import numpy as np
    from netCDF4 import Dataset
    #
    def str2(n):
        if n<10:return '0'+str(n)
        return str(n)
    #
    if filename.rfind('regional.grid.a')>-1:
        #
        # Read regional.grid.b file:

        f=open(filename[:-1]+'b','r')
        file_content=[line.rstrip() for line in f.readlines()]
        f.close()
        idm=int(file_content[0][0:5]) # Get X-dim size
        jdm=int(file_content[1][0:5]) # Get Y-dim size
        dims=(jdm,idm)
        #
        # Get field names:
        fields=[]
        for line in file_content[3:]:
            fields.append(line[0:4])
        #
        ncfn = ('regional.grid.nc')
        ncfile=Dataset(ncfn,'w',format='NETCDF3_CLASSIC') # Open file
        #
        ncfile.createDimension('X',size=idm) # Create x-dim
        ncfile.createDimension('Y',size=jdm) # Create y-dim
        #
        # Write fields into file:
        nc_field=ncfile.createVariable('X',datatype='f4',dimensions=('X')); nc_field[:]=np.arange(idm)
        nc_field=ncfile.createVariable('Y',datatype='f4',dimensions=('Y')); nc_field[:]=np.arange(jdm)
        for field in fields:
            print('Doing '+field+'.')
            ab_field=getField(field,filename,np.NaN)
            print('Shape: ' + str(ab_field.shape))
            print('(min, mean, max) = ({0:f}, {1:f}, {2:f})'.format(np.nanmin(ab_field),np.nanmean(ab_field),np.nanmax(ab_field)))
            nc_field=ncfile.createVariable(field,datatype='f4',dimensions=('Y','X'))
            nc_field[:]=ab_field
        #
        ncfile.close() # Close file
    #
    #--------------------------------------------------------------------------------------------------
    #


    elif filename.rfind('depth')>-1:

        if os.path.dirname(filename) == '':
            regional_grid_fn = 'regional.grid.b'
        else:
            regional_grid_fn = (os.path.dirname(filename) + '/regional.grid.b')
        plon=getField('plon',regional_grid_fn,np.NaN)
        plat=getField('plat',regional_grid_fn,np.NaN)

        bathy = getBathymetry(filename, undef=np.nan)
        S = bathy.shape
        jdm = S[0]
        idm = S[1]

        ncfn = (filename[0:-2]+'.nc')
        print('Working on',ncfn)
        ncfile=Dataset(ncfn,'w',format='NETCDF3_CLASSIC') # Open file
        #
        ncfile.createDimension('X',size=idm) # Create x-dim
        ncfile.createDimension('Y',size=jdm) # Create y-dim
        ##
        ## Write to NetCDF.
        ##

        nc_field=ncfile.createVariable('longitude',datatype='f4',dimensions=('Y','X'))
        nc_field[:]=plon
        nc_field=ncfile.createVariable('latitude',datatype='f4',dimensions=('Y','X'))
        nc_field[:]=plat
        nc_field=ncfile.createVariable('bathymetry',datatype='f4',dimensions=('Y','X'))
        nc_field[:]=bathy

        ncfile.close() # Close file


    #
    #--------------------------------------------------------------------------------------------------
    #


    elif filename.rfind('arch')>-1:
        #
        from matplotlib.dates import num2date
        #
        # Read archv.b file:
        f=open(filename[:-1]+'b','r')
        file_content=[line.rstrip() for line in f.readlines()]
        f.close()
        idm=int(file_content[7][0:5])    # Get X-dim size
        jdm=int(file_content[8][0:5])    # Get Y-dim size
        kdm=int(file_content[-1][33:35]) # Get Z-dim size
        dims=(kdm,jdm,idm)
        #
        if os.path.dirname(filename) == '':
            regional_grid_fn = 'regional.grid.b'
        else:
            regional_grid_fn = (os.path.dirname(filename) + '/regional.grid.b')
        plon=getField('plon',regional_grid_fn,np.NaN)
        plat=getField('plat',regional_grid_fn,np.NaN)

        if os.path.dirname(filename) == '':
            regional_depth_fn = 'regional.depth.b'
        else:
            regional_depth_fn = (os.path.dirname(filename) + '/regional.depth.b')
        bathy = getBathymetry(regional_depth_fn,undef=np.nan)
        #
        # Compute a current datetime instance:
        day_in_year=int(filename[-8:-5])
        hour=filename[-4:-2]
        year=int(filename[-13:-9])
        day_since_0001_01_01=(year-1)*365+year/4-year/100+year/400+day_in_year
        now=num2date(day_since_0001_01_01)
        date_string=str(now.year)+str2(now.month)+str2(now.day)+'_'+hour
        #
        print('Working on','archv.'+date_string+'.nc')
        ncfn = (filename[0:-2]+'.nc')
        ncfile=Dataset(ncfn,'w',format='NETCDF3_CLASSIC') # Open file
        #
        ncfile.createDimension('X',size=idm) # Create x-dim
        ncfile.createDimension('Y',size=jdm) # Create y-dim
        ncfile.createDimension('layer',size=kdm)     # Create z-dim
        ncfile.createDimension('time',size=1)       # Create dummy time axis
        ##
        ## Read each field and write to NetCDF.
        ##
        fields=[]
        for line in file_content[10:]:
            this_field = line[0:8].replace('.','').rstrip()
            if not this_field in fields:
                fields.append(this_field)

        nc_field=ncfile.createVariable('longitude',datatype='f4',dimensions=('Y','X'))
        nc_field[:]=plon[0:jdm,0:idm]
        nc_field=ncfile.createVariable('latitude',datatype='f4',dimensions=('Y','X'))
        nc_field[:]=plat[0:jdm,0:idm]
        nc_field=ncfile.createVariable('bathymetry',datatype='f4',dimensions=('Y','X'))
        nc_field[:]=bathy[0:jdm,0:idm]
        nc_field=ncfile.createVariable('layer',datatype='f4',dimensions=('layer',))
        nc_field[:]=np.arange(1,kdm+1)


        for field in fields:
            print('Doing '+field+'.')
            ab_field=getField(field,filename,np.NaN)
            s = ab_field.shape
            print('Shape: ' + str(s))
            print('(min, mean, max) = ({0:f}, {1:f}, {2:f})'.format(np.nanmin(ab_field),np.nanmean(ab_field),np.nanmax(ab_field)))
            if len(s) < 3:
                nc_field=ncfile.createVariable(field,datatype='f4',dimensions=('time','Y','X'))
            else:
                nc_field=ncfile.createVariable(field,datatype='f4',dimensions=('time','layer','Y','X'))
            print(nc_field)
            nc_field[:]=ab_field
        ncfile.close() # Close file
        #
        #--------------------------------------------------------------------------------------------------
        #
        #if filename.rfind('forcing')>-1:


    elif filename.rfind('restart')>-1:
        #
        from matplotlib.dates import num2date
        #
        # Read archv.b file:
        f=open(filename[:-1]+'b','r')
        file_content=[line.rstrip() for line in f.readlines()]
        f.close()
        for iiii in range(len(file_content)):
            if file_content[iiii].rfind('layer,tlevel,range')>-1:
                sindx = iiii
                break
        kdm=41 #len(file_content)-sindx ;  # int(file_content[-1][33:35]) # Get number of entries.
        print('Working on file: '+filename)
        #
        if os.path.dirname(filename) == '':
            regional_grid_fn = 'regional.grid.b'
        else:
            regional_grid_fn = (os.path.dirname(filename) + '/regional.grid.b')
        plon=getField('plon',regional_grid_fn,np.NaN)
        plat=getField('plat',regional_grid_fn,np.NaN)
        dims = plon.shape
        print('Dims: ', dims)
        jdm = dims[0]
        idm = dims[1]

        if os.path.dirname(filename) == '':
            regional_depth_fn = 'regional.depth.b'
        else:
            regional_depth_fn = (os.path.dirname(filename) + '/regional.depth.b')
        bathy = getBathymetry(regional_depth_fn,undef=np.nan)
        ncfn = (filename[0:-2]+'.nc')
        ncfile=Dataset(ncfn,'w',format='NETCDF3_CLASSIC') # Open file
        #
        ncfile.createDimension('X',size=idm) # Create x-dim
        ncfile.createDimension('Y',size=jdm) # Create y-dim
        ncfile.createDimension('layer',size=kdm)     # Create z-dim
        ncfile.createDimension('time',size=1)       # Create dummy time axis
        ##
        ## Read each field and write to NetCDF.
        ##
        fields=[]
        for line in file_content[10:]:
            this_field = line[0:8].replace('.','').rstrip()
            if not this_field in fields:
                fields.append(this_field)

        nc_field=ncfile.createVariable('longitude',datatype='f4',dimensions=('Y','X'))
        nc_field[:]=plon[0:jdm,0:idm]
        nc_field=ncfile.createVariable('latitude',datatype='f4',dimensions=('Y','X'))
        nc_field[:]=plat[0:jdm,0:idm]
        nc_field=ncfile.createVariable('bathymetry',datatype='f4',dimensions=('Y','X'))
        nc_field[:]=bathy[0:jdm,0:idm]
        nc_field=ncfile.createVariable('layer',datatype='f4',dimensions=('layer',))
        nc_field[:]=np.arange(1,kdm+1)


        for field in fields:
            print('Doing '+field+'.')
            ab_field=getFieldRestart(field,filename,[jdm,idm,kdm],np.NaN)
            s = ab_field.shape
            print('Shape: ' + str(s))
            print('(min, mean, max) = ({0:f}, {1:f}, {2:f})'.format(np.nanmin(ab_field),np.nanmean(ab_field),np.nanmax(ab_field)))
            if len(s) < 3:
                nc_field=ncfile.createVariable(field,datatype='f4',dimensions=('time','Y','X'))
            else:
                nc_field=ncfile.createVariable(field,datatype='f4',dimensions=('time','layer','Y','X'))
            print(nc_field)
            nc_field[:]=ab_field
        ncfile.close() # Close file
        #
        #--------------------------------------------------------------------------------------------------
        #
        #if filename.rfind('forcing')>-1:



    elif filename.rfind('forcing')>-1: # or filename.rfind('restart')>-1:
        #
        # Read forcing.[field].b file:
        f=open(filename[:-1]+'b','r')
        file_content=[line.rstrip() for line in f.readlines()]
        f.close()

        ## Get dimensions.
        for iiii in range(len(file_content)):
            if file_content[iiii].rfind('i/jdm')>-1:
                sindx = iiii
                break

        idm=int(file_content[sindx].split(' ')[-2])  # Get X-dim size
        jdm=int(file_content[sindx].split(' ')[-1])  # Get Y-dim size
        sindx += 1 # Data begins on the next line after the domain size info.

        kdm=len(file_content)-sindx ;  # int(file_content[-1][33:35]) # Get number of entries.
        dims=(jdm,idm)
        print('Working on file: '+filename,dims)
        #
        if os.path.dirname(filename) == '':
            regional_grid_fn = 'regional.grid.b'
        else:
            regional_grid_fn = (os.path.dirname(filename) + '/regional.grid.b')
        plon=getField('plon',regional_grid_fn,np.NaN)
        plat=getField('plat',regional_grid_fn,np.NaN)
        #
        ncfn=filename[:-1]+'nc'
        ncfile=Dataset(ncfn,'w',format='NETCDF3_CLASSIC') # Open file
        #
        ncfile.createDimension('Longitude',size=idm) # Create x-dim
        ncfile.createDimension('Latitude',size=jdm)  # Create y-dim
        ncfile.createDimension('Record',size=kdm)        # Create t-dim (unlimitted)
        #
        nc_field=ncfile.createVariable(filename[-8:-2],\
                                       datatype='f4',\
                                       dimensions=('Record','Latitude','Longitude'))
        #
        file_content=file_content[sindx:]
        record=0
        for line in file_content:
            ab_field=getRecord(filename,dims,record,undef=np.nan)
            print(filename,record,np.min(ab_field),np.max(ab_field))
            nc_field[record,:,:]=ab_field #[:,:]
            record=record+1
        ncfile.close() # Close file
        #



    if filename.rfind('relax')>-1:
        #
        # Read forcing.[field].b file:
        f=open(filename[:-1]+'b','r')
        file_content=[line.rstrip() for line in f.readlines()]
        f.close()
        idm=int(file_content[4].split()[2])  # Get X-dim size
        jdm=int(file_content[4].split()[3]) # Get Y-dim size
        kdm=41 #int(file_content[-1][33:35]) # Get number of levels.
        dims=(jdm,idm)
        print('Working on file: '+filename,dims)
        #
        regional_grid_fn = (os.path.dirname(filename) + '/regional.grid.b')
        plon=getField('plon',regional_grid_fn,np.NaN)
        plat=getField('plat',regional_grid_fn,np.NaN)
        #
        ncfn = (filename[0:-2]+'.nc')
        print('Working on',ncfn)
        ncfile=Dataset(ncfn,'w',format='NETCDF3_CLASSIC') # Open file
        #
        ncfile.createDimension('Longitude',size=idm) # Create x-dim
        ncfile.createDimension('Latitude',size=jdm)  # Create y-dim
        ncfile.createDimension('Layer',size=kdm)  # Create y-dim
        ncfile.createDimension('Time',size=0)        # Create t-dim (unlimitted)
        #
        nc_field=ncfile.createVariable(filename[-8:-2],\
                                       datatype='f4',\
                                       dimensions=('Time','Latitude','Longitude'))
        #
        file_content=file_content[5:]
        record=0
        for line in file_content:
            ab_field=getRecord(filename,dims,record,undef=np.nan)
            print(filename,record,np.min(ab_field),np.max(ab_field))
            nc_field[record,:,:]=ab_field #[:,:]
            record=record+1
        ncfile.close() # Close file
        #



    else:
        #
        # Read forcing.[field].b file:
        f=open(filename[:-1]+'b','r')
        file_content=[line.rstrip() for line in f.readlines()]
        f.close()
        for iiii in range(len(file_content)):
            if file_content[iiii].rfind('min, max')>-1 or file_content[iiii].rfind('layer,tlevel,range')>-1:
                sindx = iiii
                break
        kdm=len(file_content)-sindx ;  # int(file_content[-1][33:35]) # Get number of entries.
        print('Working on file: '+filename)
        #
        if os.path.dirname(filename) == '':
            regional_grid_fn = 'regional.grid.b'
        else:
            regional_grid_fn = (os.path.dirname(filename) + '/regional.grid.b')
        plon=getField('plon',regional_grid_fn,np.NaN)
        plat=getField('plat',regional_grid_fn,np.NaN)
        dims = plon.shape
        print('Dims: ', dims)
        jdm = dims[0]
        idm = dims[1]
        #
        ncfn=filename[:-1]+'nc'
        ncfile=Dataset(ncfn,'w',format='NETCDF3_CLASSIC') # Open file
        #
        ncfile.createDimension('Longitude',size=idm) # Create x-dim
        ncfile.createDimension('Latitude',size=jdm)  # Create y-dim
        ncfile.createDimension('Record',size=kdm)        # Create t-dim (unlimitted)
        #
        nc_field=ncfile.createVariable(filename[-8:-2],\
                                       datatype='f4',\
                                       dimensions=('Record','Latitude','Longitude'))
        #
        file_content=file_content[sindx:]
        record=0
        for line in file_content:
            ab_field=getRecord(filename,dims,record,undef=np.nan)
            print(filename,record,np.min(ab_field),np.max(ab_field))
            nc_field[record,:,:]=ab_field #[:,:]
            record=record+1
        ncfile.close() # Close file
        #


    return ncfn



#
########################################################################
#


def sigma2_12term(t,s):

    """
    See: src/components/hycom/src_2.2.34/ALT_CODE/stmt_fns_SIGMA2_12term.h
    FORTRAN Code:
        c
        c --- -----------------
        c --- equation of state
        c --- -----------------
        c
        c --- sigma at rpdb (dbar) as a function of temp (deg c) and salinity (psu)
        c
              sig_n(t,s) = c101+(c102+c004*t+c005*s)*t  +
             &                  (c103+       c006*s)*s
              sig_d(t,s) = c111+(c112+c014*t+c015*s)*t  +
             &                  (c113       +c016*s)*s
              sig_q(t,s) = aone/sig_d(t,s)
              sig(  t,s) = sig_n(t,s)*sig_q(t,s)

    Note: 17 term uses an iterative process with this 12 term formulation as first guess.
    """

    ## Constants.

    #c --- coefficients for 18-term rational function sigloc().
    c001=-1.4627567840659594e-01   #!num. constant    coefficent
    c002= 6.4247392832635697e-02   #!num.    T        coefficent
    c003= 8.1213979591704621e-01   #!num.       S     coefficent
    c004=-8.1321489441909698e-03   #!num.    T^2      coefficent
    c005= 4.5199845091090296e-03   #!num.    T  S     coefficent
    c006= 4.6347888132781394e-04   #!num.       S^2   coefficent
    c007= 5.0879498675039621e-03   #!num. P           coefficent
    c008= 1.6333913018305079e-05   #!num. P  T        coefficent
    c009= 4.3899924880543972e-06   #!num. P     S     coefficent

    c011= 1.0000000000000000e+00   #!den. constant    coefficent
    c012= 1.0316374535350838e-02   #!den.    T        coefficent
    c013= 8.9521792365142522e-04   #!den.       S     coefficent
    c014=-2.8438341552142710e-05   #!den.    T^2      coefficent
    c015=-1.1887778959461776e-05   #!den.    T  S     coefficent
    c016=-4.0163964812921489e-06   #!den.       S^2   coefficent
    c017= 1.1995545126831476e-05   #!den. P           coefficent
    c018= 5.5234008384648383e-08   #!den. P  T        coefficent
    c019= 8.4310335919950873e-09   #!den. P     S     coefficent


    #c --- reference pressure.
    prs2pdb=1.0e-4     #!Pascals to dbar
    #csig0 real, parameter :: pref=   0.d0      !ref. pressure in Pascals, sigma0
    pref=2000.0e4      #!ref. pressure in Pascals, sigma2
    rpdb=pref*prs2pdb #!ref. pressure in dbar

    # Derived Coefficients
    c101=c001+rpdb*c007,           #num. constant    coefficent
    c102=c002+rpdb*c008,           #num.    T        coefficent
    c103=c003+rpdb*c009            #num.       S     coefficent
    c111=c011+rpdb*c017,           #num. constant    coefficent
    c112=c012+rpdb*c018,           #num.    T        coefficent
    c113=c013+rpdb*c019            #num.       S     coefficent


    ##
    ## Do the calculations.
    ##

    sig_n = c101+(c102+c004*t+c005*s)*t  +  (c103+c006*s)*s
    sig_d = c111+(c112+c014*t+c015*s)*t  +  (c113+c016*s)*s
    sig_q = 1.0/sig_d
    sig = sig_n*sig_q

    return sig


def forday(datetime_to_convert, yrflag=3):
    """
    Convert python datetime to HYCOM model day.
    NOTE: So var this only works for yrflag=3!!!
    """
    import datetime as dt

    if yrflag == 3:
        """
        HYCOM model day 1.000000 is 00 UTC 1/1/1901.
        """
        model_day = 1.0 + (datetime_to_convert - dt.datetime(1901,1,1,0,0,0)).total_seconds()/86400.0
    else:
        print('WARNING: yrflag = {} is not implemented. Returning -999.0.'.format(yrflag))
        model_day = -999.0

    return model_day



def append_field_to_a_file(fn,data,lev):
    import numpy.ma as ma

    if lev < 0:
        data2d = 1.0*data
    else:
        data2d = 1.0*data[lev,:,:]

    ## Assign the masked data value.
    data2d = data2d.astype('float32')
    ma.set_fill_value(data2d, np.float32(2**100))

    S = data2d.shape
    jdm = S[0]
    idm = S[1]
    reclen = 4*idm*jdm
    ## HYCOM binary data is written out in chunks/"words" of multiples of 4096*4 bytes.
    ## In general, the length of one level of one variable (reclen) will fall between
    ## consecutive multiples of the wordlen. The data is padded to bring the volume
    ## up to the next multiple. The "pad" value below is how many bytes are needed to do this.
    wordlen = 4096*4
    pad = int(wordlen * np.ceil(reclen / wordlen) - reclen)   # Pad size in bytes

    file = open(fn,'ab') # Open file

    ## Binary representation of the DATA
    bytes = data2d.filled().byteswap().tobytes()

    ## Binary representation of the PAD section.
    bytes += pad * b'\0'
    file.write(bytes)
    file.close()


    ## ASCII representation of the data written.
    np.savetxt('out.txt',data2d.filled(),fmt='%16.7e')



def append_field_to_b_file(fn,data,lev,varname,this_datetime,baclin,dens,k_override=-1):
    if lev < 0:
        data2d = 1.0*data
        k = 0
    else:
        data2d = 1.0*data[lev,:,:]
        k = lev+1

    ## Option to override the value of "k" reported in the b file.
    ## So far, this is only used to specify "sigver" for the equation of state
    ## in the "montg1" variable.
    if k_override > 0:
        k = k_override

    ## Get model day and time step.
    model_day = forday(this_datetime)
    model_time_step = int(model_day * 86400.0 / baclin)

    FMT='{0:8s} = {1:10d} {2:10.3f} {3:2d} {4:5.2f}{5:16.7e}{6:16.7e}'

    print(FMT.format(varname,model_time_step,model_day,k,dens,np.nanmin(data2d),np.nanmax(data2d)))
    fileb = open(fn,'a')
    fileb.write('\n')
    fileb.write(FMT.format(varname,model_time_step,model_day,k,dens,np.nanmin(data2d),np.nanmax(data2d)))
    fileb.close()



def get_interp_weights(lon,lat,mask,lonI,latI,maskI):
    """
    Calculate interp inverse distance weights using four nearest
    NON MASKED neighbors.
    TODO: Finish this function.
    """

    lon2d,lat2d = np.meshgrid(lon,lat)
    lon2dmasked = ma.masked_array(lon2d, mask=mask)
    lat2dmasked = ma.masked_array(lat2d, mask=mask)

    lon1dcompressed = lon2dmasked.compressed()
    lat1dcompressed = lat2dmasked.compressed()
    nk = len(lon1dcompressed)

    S = lonI.shape

    return NaN


def do_interp_the_real_one(lon,lat,data,lonI,latI):
    from scipy.interpolate import LinearNDInterpolator
    from numpy import ma

    ## Subset
    pad = 0.1  # Deg. to pad either side, for interpolation.
    lon_min = np.nanmin(lonI)
    lon_max = np.nanmax(lonI)
    lat_min = np.nanmin(latI)
    lat_max = np.nanmax(latI)

    lon_keep = np.where(np.logical_and(lon > lon_min-pad, lon < lon_max+pad))[0]
    lat_keep = np.where(np.logical_and(lat > lat_min-pad, lat < lat_max+pad))[0]

    lon0 = lon[lon_keep[0]:lon_keep[-1]+1]
    lat0 = lat[lat_keep[0]:lat_keep[-1]+1]
    data0 = data[lat_keep[0]:lat_keep[-1]+1,lon_keep[0]:lon_keep[-1]+1]
    data_compressed = data0.compressed()

    # Source Points Array
    lon2d,lat2d = np.meshgrid(lon0,lat0)
    lon2dmasked = ma.masked_array(lon2d, mask=data0.mask)
    lat2dmasked = ma.masked_array(lat2d, mask=data0.mask)
    lon1dcompressed = lon2dmasked.compressed()
    lat1dcompressed = lat2dmasked.compressed()
    points = np.array([lon1dcompressed,lat1dcompressed]).T

    # Destination Points Array
    lon1d = lonI.flatten()
    lat1d = latI.flatten()
    pointsI = np.array([lon1d,lat1d]).T

    # Do the interpolation.
    F = LinearNDInterpolator(points, data_compressed)
    dataI1d = F(pointsI)
    dataI = np.reshape(dataI1d,lonI.shape)

    return dataI



def do_interp(lon,lat,data,lonI,latI):
    """
    This is the "quick hack" version.

    For Longitude, I'm just going to use the subset matching the longitudes in the file.
    Latitudes are different! Do a 1-D interp to get latitude to work out.
    """
    from numpy import ma

    ## Subset
    pad = 0.01  # Deg. to pad either side, for interpolation.
    lon_min = np.nanmin(lonI)
    lon_max = np.nanmax(lonI)
    lat_min = np.nanmin(latI)
    lat_max = np.nanmax(latI)

    lon_keep = np.where(np.logical_and(lon > lon_min-pad, lon < lon_max+pad))[0]
    lat_keep = np.where(np.logical_and(lat > lat_min-pad, lat < lat_max+pad))[0]

    ## Just take the subset of points that is the same size as (latI,lonI).
    S=lonI.shape

    linear_factors = np.interp(latI[:,0], lat, np.arange(len(lat)))
    lat_indices = np.round(linear_factors).astype(int)

    #data1 = data.filled()[lat_indices,:]
    data1 = data[lat_indices,:]
    dataI = data1[:,lon_keep[0]:lon_keep[-1]+1]

    return dataI




def ncz2ab(filename,baclin=60,interp=True):
    """
    Convert NetCDF z level data from hycom.org in to binary [ab] files
    so they can be used with "remaph" to generate hybrid layer data.

    filename can be any of the files, the function will use the path to search
    for a set of file like this:
        hycom_glby_930_2020060712_t024_ssh.nc
        hycom_glby_930_2020060712_t024_ts3z.nc
        hycom_glby_930_2020060712_t024_uv3z.nc

    interp=True    | Interp horizontally to regional.grid.[ab].
    interp=False   | Do not interp. May crash if regional.depth.[ab] is inconsistent size.
    Interpolation is 2-D bilinear, level by level.
    """
    import datetime as dt
    from netCDF4 import Dataset
    from scipy.interpolate import LinearNDInterpolator
    from scipy.interpolate import RectBivariateSpline
    from numpy import ma
    import matplotlib.pyplot as plt


    ## Get the file names.
    last_part = filename.split('_')[-1]
    fn_partial = filename[0:-1*len(last_part)-1]
    fn_ssh = (fn_partial + '_ssh.nc')
    fn_sur = (fn_partial.replace('glby','GLBy0.08') + '_sur.nc')
    fn_uv = (fn_partial + '_uv3z.nc')
    fn_ts = (fn_partial + '_ts3z.nc')

    # Get time step and day.
    ymdh = fn_ssh.split('_')[-3]
    fcst_str = fn_ssh.split('_')[-2]
    fcst = int(fcst_str[1:])
    this_datetime = dt.datetime.strptime(ymdh,'%Y%m%d%H') + dt.timedelta(hours=fcst)
    print(this_datetime)

    ###
    ### Read in the data.
    ###

    # SSH
    print(fn_ssh)
    DS=Dataset(fn_ssh)
    lon = DS['lon'][:]
    lat = DS['lat'][:]
    ssh = DS['surf_el'][:][0]
    DS.close()

    # Surface
    print(fn_sur)
    DS=Dataset(fn_sur)
    lon_sur = DS['lon'][:]
    lat_sur = DS['lat'][:]
    steric = DS['steric_ssh'][:][0]
    surflx = DS['qtot'][:][0]
    salflx = DS['emp'][:][0]
    bl_dpth = DS['surface_boundary_layer_thickness'][:][0]
    mix_dpth = DS['mixed_layer_thickness'][:][0]
    u_btrop = DS['u_barotropic_velocity'][:][0]
    v_btrop = DS['v_barotropic_velocity'][:][0]
    DS.close()

    ## 3-D Data
    print(fn_ts)
    DS=Dataset(fn_ts)
    z = DS['depth'][:]
    t = DS['water_temp'][:][0]
    t_bottom = DS['water_temp_bottom'][:][0]
    s = DS['salinity'][:][0]
    s_bottom = DS['salinity_bottom'][:][0]
    DS.close()
    print(fn_uv)
    DS=Dataset(fn_uv)
    u = DS['water_u'][:][0]
    u_bottom = DS['water_u_bottom'][:][0]
    v = DS['water_v'][:][0]
    v_bottom = DS['water_v_bottom'][:][0]
    DS.close()
    kdm = len(z)
    bathy = getBathymetry('regional.depth.a')

    ###
    ### Interp if specified.
    ###
    if interp:

        lonI = getField('plon','regional.grid.a')+360.0 ## 2-D, not necessarily rectangular.
        latI = getField('plat','regional.grid.a') ## 2-D, not necessarily rectangular.

        ## Interpolate surface/2d fields.
        print('Interp ssh.')
        ssh = do_interp(lon,lat,ssh,lonI,latI)
        print('Interp t_bottom.')
        t_bottom = do_interp(lon,lat,t_bottom,lonI,latI)
        print('Interp s_bottom.')
        s_bottom = do_interp(lon,lat,s_bottom,lonI,latI)
        print('Interp u_bottom.')
        u_bottom = do_interp(lon,lat,u_bottom,lonI,latI)
        print('Interp v_bottom.')
        v_bottom = do_interp(lon,lat,v_bottom,lonI,latI)
        print('Interp steric.')
        steric = do_interp(lon_sur,lat_sur,steric,lonI,latI)
        print('Interp mixflx.')
        surflx = do_interp(lon_sur,lat_sur,surflx,lonI,latI)
        print('Interp salflx.')
        salflx = do_interp(lon_sur,lat_sur,salflx,lonI,latI)
        print('Interp bl_dpth.')
        bl_dpth = do_interp(lon_sur,lat_sur,bl_dpth,lonI,latI)
        print('Interp mix_dpth.')
        mix_dpth = do_interp(lon_sur,lat_sur,mix_dpth,lonI,latI)
        print('u_btrop.')
        u_btrop = do_interp(lon_sur,lat_sur,u_btrop,lonI,latI)
        print('v_btrop.')
        v_btrop = do_interp(lon_sur,lat_sur,v_btrop,lonI,latI)

        ## Now do the 3-D fields.
        print('Interp 3-D Fields.')
        SI = ssh.shape
        tI = np.nan*np.zeros([kdm,SI[0],SI[1]])
        sI = np.nan*np.zeros([kdm,SI[0],SI[1]])
        uI = np.nan*np.zeros([kdm,SI[0],SI[1]])
        vI = np.nan*np.zeros([kdm,SI[0],SI[1]])

        #for k in [0,1,2]:
        for k in range(kdm):
            print('--> Level {} of {}.'.format(k+1,kdm))
            tI[k] = do_interp(lon,lat,t[k,:,:],lonI,latI)
            sI[k] = do_interp(lon,lat,s[k,:,:],lonI,latI)
            uI[k] = do_interp(lon,lat,u[k,:,:],lonI,latI)
            vI[k] = do_interp(lon,lat,v[k,:,:],lonI,latI)

        t = tI.copy()
        s = sI.copy()
        u = uI.copy()
        v = vI.copy()

    ## Get Density.
    sigma = sigma2_12term(t,s)

    ## Gonna need this info below.
    S = t.shape
    ny = S[1]
    nx = S[2]


    ###
    ### Further mask using topo mask.
    ###
    ssh = ma.masked_array(ssh, mask=~np.isfinite(bathy))
    t_bottom = ma.masked_array(t_bottom, mask=~np.isfinite(bathy))
    s_bottom = ma.masked_array(s_bottom, mask=~np.isfinite(bathy))
    u_bottom = ma.masked_array(u_bottom, mask=~np.isfinite(bathy))
    v_bottom = ma.masked_array(v_bottom, mask=~np.isfinite(bathy))
    steric = ma.masked_array(steric, mask=~np.isfinite(bathy))
    surflx = ma.masked_array(surflx, mask=~np.isfinite(bathy))
    salflx = ma.masked_array(salflx, mask=~np.isfinite(bathy))
    bl_dpth = ma.masked_array(bl_dpth, mask=~np.isfinite(bathy))
    mix_dpth = ma.masked_array(mix_dpth, mask=~np.isfinite(bathy))
    u_btrop = ma.masked_array(u_btrop, mask=~np.isfinite(bathy))
    v_btrop = ma.masked_array(v_btrop, mask=~np.isfinite(bathy))


    ###
    ### Manage layering.
    ###

    ## Layer Thickness
    dp = 0.0*t
    dz = 0.0*t
    z_bottom = 0.0*t
    z_top = 0.0*t
    z_mask = 0.0*t

    """
    for k in range(0, kdm-1):
        dz = z[k+1] - z[k]
        dp[k,:,:] = 1.0*dz
        z_top[k,:,:] = z[k]
        z_bottom[k,:,:] = z[k+1]

        ## Refine if it I'm near the bottom.
        for jj in range(ny):
            for ii in range(nx):
                if z_top[k,jj,ii] < bathy[jj,ii] and z_bottom[k,jj,ii] > bathy[jj,ii]:
                    dp[k,jj,ii] = bathy[jj,ii] - z[k]
                if z_top[k,jj,ii] > bathy[jj,ii]:
                    dp[k,jj,ii] = 0.0
    """

    ## treat z=0 as 0 to half of first depth.
    z_top[0,:,:] = 0.0
    z_bottom[0,:,:] = 0.5*z[1]

    ## Do the middle
    for k in range(1, kdm-1):
        z_top[k,:,:] = 0.5*(z[k] + z[k-1])
        z_bottom[k,:,:] = 0.5*(z[k] + z[k+1])

    ## Treat last level as half way beteen (kdm-1,kdm) to the bottom.
    z_top[kdm-1,:,:] = 0.5*(z[kdm-1] + z[kdm-2])
    z_bottom[kdm-1,:,:] = bathy

    dz = z_bottom - z_top

    ## Refine if I'm near the bottom.
    for k in range(kdm):
        for jj in range(ny):
            for ii in range(nx):
                if z_top[k,jj,ii] < bathy[jj,ii] and z_bottom[k,jj,ii] > bathy[jj,ii]:
                    dz[k,jj,ii] = bathy[jj,ii] - z_top[k,jj,ii] + 10.0
                if z_top[k,jj,ii] > bathy[jj,ii]:
                    dz[k,jj,ii] = 0.0


    # dp *= 9806 # meters to pressure.
    dp = dz * 9806

    ###
    ### Bottom of the sea mask for 3-D variables.
    ###

    for k in range(0, kdm):
        z_mask_2d = 0.0*bathy
        z_mask_2d[~np.isfinite(bathy)] = 1
        z_mask[k,:,:] = z_mask_2d
    z_mask = z_mask > 0.5

    dp = ma.masked_array(dp.data,mask=z_mask)
    t = ma.masked_array(t.data,mask=z_mask)
    s = ma.masked_array(s.data,mask=z_mask)
    u = ma.masked_array(u.data,mask=z_mask)
    v = ma.masked_array(v.data,mask=z_mask)
    sigma = ma.masked_array(sigma.data,mask=z_mask)
    sigma_bottom = sigma2_12term(t_bottom, s_bottom)

    ## Interpolate to get layer MEAN values.
    ## I also take this opportunity to subtract out the barotropic currents
    ## as "u-vel." and "v-vel." represent the baroclinic currents.
    """
    t_layer_mean = 0.0*t
    s_layer_mean = 0.0*t
    u_layer_mean = 0.0*t
    v_layer_mean = 0.0*t

    for k in range(0, kdm-1):
        t_layer_mean[k,:,:] = 0.5 * (t[k,:,:] + t[k+1,:,:])
        s_layer_mean[k,:,:] = 0.5 * (s[k,:,:] + s[k+1,:,:])
        u_layer_mean[k,:,:] = 0.5 * (u[k,:,:] + u[k+1,:,:]) - u_btrop
        v_layer_mean[k,:,:] = 0.5 * (v[k,:,:] + v[k+1,:,:]) - v_btrop
    t_layer_mean[kdm-1,:,:] = t[kdm-1,:,:]
    s_layer_mean[kdm-1,:,:] = s[kdm-1,:,:]
    u_layer_mean[kdm-1,:,:] = u[kdm-1,:,:]
    v_layer_mean[kdm-1,:,:] = v[kdm-1,:,:]
    """

    ## Fill in bottom values.

    """
    for k in range(0, kdm):
        t_layer_mean_2d = t_layer_mean[k,:,:]
        t_layer_mean_2d[bathy - z_bottom[k,:,:] < 0.0] = t_bottom[bathy - z_bottom[k,:,:] < 0.0]
        ## Hack to fix some remaining isolated weird values.
        ## (Presumably at the edges of bathymetry features near the bottom)
        ## (ALSO DONE FOR S, U, V BELOW!!!)
        hack_points = [t_layer_mean_2d < -100.0]
        t_layer_mean_2d[hack_points] = t_bottom[hack_points]
        t_layer_mean[k,:,:] = t_layer_mean_2d

        s_layer_mean_2d = s_layer_mean[k,:,:]
        s_layer_mean_2d[bathy - z_bottom[k,:,:] < 0.0] = s_bottom[bathy - z_bottom[k,:,:] < 0.0]
        s_layer_mean_2d[hack_points] = s_bottom[hack_points]
        s_layer_mean[k,:,:] = s_layer_mean_2d

        u_layer_mean_2d = u_layer_mean[k,:,:]
        u_layer_mean_2d[bathy - z_bottom[k,:,:] < 0.0] = u_bottom[bathy - z_bottom[k,:,:] < 0.0]
        u_layer_mean_2d[hack_points] = u_bottom[hack_points]
        u_layer_mean[k,:,:] = u_layer_mean_2d

        v_layer_mean_2d = v_layer_mean[k,:,:]
        v_layer_mean_2d[bathy - z_bottom[k,:,:] < 0.0] = v_bottom[bathy - z_bottom[k,:,:] < 0.0]
        v_layer_mean_2d[hack_points] = v_bottom[hack_points]
        v_layer_mean[k,:,:] = v_layer_mean_2d
    """

    for k in range(0, kdm):
        t_2d = t[k,:,:]
        t_2d[bathy - z_bottom[k,:,:] < 0.0] = t_bottom[bathy - z_bottom[k,:,:] < 0.0]
        ## Hack to fix some remaining isolated weird values.
        ## (Presumably at the edges of bathymetry features near the bottom)
        ## (ALSO DONE FOR S, U, V BELOW!!!)
        hack_points = [t_2d < -100.0]
        t_2d[hack_points] = t_bottom[hack_points]
        t[k,:,:] = t_2d

        s_2d = s[k,:,:]
        s_2d[bathy - z_bottom[k,:,:] < 0.0] = s_bottom[bathy - z_bottom[k,:,:] < 0.0]
        s_2d[hack_points] = s_bottom[hack_points]
        s[k,:,:] = s_2d

        sigma_2d = sigma[k,:,:]
        sigma_2d[bathy - z_bottom[k,:,:] < 0.0] = np.nan #sigma_bottom[bathy - z_bottom[k,:,:] < 0.0]
        sigma_2d[hack_points] = np.nan #sigma_bottom[hack_points]
        sigma[k,:,:] = sigma_2d

        u_2d = u[k,:,:]
        u_2d[bathy - z_bottom[k,:,:] < 0.0] = u_bottom[bathy - z_bottom[k,:,:] < 0.0]
        u_2d[hack_points] = u_bottom[hack_points]
        u[k,:,:] = u_2d

        v_2d = v[k,:,:]
        v_2d[bathy - z_bottom[k,:,:] < 0.0] = v_bottom[bathy - z_bottom[k,:,:] < 0.0]
        v_2d[hack_points] = v_bottom[hack_points]
        v[k,:,:] = v_2d



    # plt.pcolormesh(u_btrop) ; plt.colorbar() ;  plt.show()
    # plt.pcolormesh(u_layer_mean[38,:,:]) ; plt.colorbar() ;  plt.show()
    # plt.pcolormesh(t_layer_mean[38,:,:]) ; plt.colorbar() ;  plt.show()


    ############################################################################

    n_levels = len(z)
    print('Saving surface data and {} layers.'.format(n_levels))

    ###
    ### Write Output.
    ###

    # Start the files.
    fna = this_datetime.strftime('archv.%Y_%j_%H.a')
    fnb = this_datetime.strftime('archv.%Y_%j_%H.b')

    fileb = open(fnb,'w')
    fileb.write("0.281c NAVGEM wind, thermal, precip 3-hrly forcing ; LWcorr; GDEM42 SSS relax;\n")
    fileb.write("17T Sigma2*; GDEM4 Jan init; KPP; SeaWiFS KPAR; HYCOM+CICE; A=20;Smag=.05;\n")
    fileb.write("Z(7):1-7,Z(16):8,Z(2):10-16,Z(13):dp00/f/x=36/1.18/262;Z(3):400-600m; NOGAPSsnow\n")
    fileb.write("GLBa0.08 archive subregioned to NWPa0.08\n")
    fileb.write("   22    'iversn' = hycom version number x10\n")
    fileb.write("  930    'iexpt ' = experiment number x10\n")
    fileb.write("    3    'yrflag' = days in year flag\n")
    fileb.write(" {0:4d}    'idm   ' = longitudinal array size\n".format(nx))
    fileb.write(" {0:4d}    'jdm   ' = latitudinal  array size\n".format(ny))
    fileb.write("field       time step  model day  k  dens        min              max")
    fileb.close()

    filea = open(fna,'wb')
    filea.close()

    #### Write surface variables.
    ## First variable is required to be the Montgomery Potential "montg1"
    ## It looks like HYCOM discards the *values* and will calculate it on its own.
    ## Therefore, I'm trying a bunch of zeros here!
    ## For montg1, the equation of state is specified by "k  dens" = sigver  thbase
    ##   which for global HYCOM is 6, 34.
    ##   so we need to override k and dens in the "b" file.
    append_field_to_b_file(fnb,0.0*ssh,-1,'montg1',this_datetime,baclin,34.0,k_override=6)
    append_field_to_a_file(fna,0.0*ssh,-1)

    ## Surface variables are assigned density of zero.
    append_field_to_b_file(fnb,(100.0/9.8)*ssh,-1,'srfhgt',this_datetime,baclin,0.0)
    append_field_to_a_file(fna,(100.0/9.8)*ssh,-1)
    append_field_to_b_file(fnb,(100.0/9.8)*steric,-1,'steric',this_datetime,baclin,0.0)
    append_field_to_a_file(fna,(100.0/9.8)*steric,-1)
    append_field_to_b_file(fnb,surflx,-1,'surflx',this_datetime,baclin,0.0)
    append_field_to_a_file(fna,surflx,-1)
    append_field_to_b_file(fnb,salflx,-1,'salflx',this_datetime,baclin,0.0)
    append_field_to_a_file(fna,salflx,-1)
    append_field_to_b_file(fnb,9806.0*bl_dpth,-1,'bl_dpth',this_datetime,baclin,0.0)
    append_field_to_a_file(fna,9806.0*bl_dpth,-1)
    append_field_to_b_file(fnb,9806.0*mix_dpth,-1,'mix_dpth',this_datetime,baclin,0.0)
    append_field_to_a_file(fna,9806.0*mix_dpth,-1)
    append_field_to_b_file(fnb,u_btrop,-1,'u_btrop',this_datetime,baclin,0.0)
    append_field_to_a_file(fna,u_btrop,-1)
    append_field_to_b_file(fnb,v_btrop,-1,'v_btrop',this_datetime,baclin,0.0)
    append_field_to_a_file(fna,v_btrop,-1)

    # Vertical levels.
    """
    for k in range(0,40):
        sigma_mean = np.nanmean(sigma[k,:,:])
        append_field_to_b_file(fnb,u_layer_mean,k,'u-vel.',this_datetime,baclin,sigma_mean)
        append_field_to_a_file(fna,u_layer_mean,k)
        append_field_to_b_file(fnb,v_layer_mean,k,'v-vel.',this_datetime,baclin,sigma_mean)
        append_field_to_a_file(fna,v_layer_mean,k)
        append_field_to_b_file(fnb,dp,k,'thknss',this_datetime,baclin,sigma_mean)
        append_field_to_a_file(fna,dp,k)
        append_field_to_b_file(fnb,t_layer_mean,k,'temp',this_datetime,baclin,sigma_mean)
        append_field_to_a_file(fna,t_layer_mean,k)
        append_field_to_b_file(fnb,s_layer_mean,k,'salin',this_datetime,baclin,sigma_mean)
        append_field_to_a_file(fna,s_layer_mean,k)
    """

    for k in range(0,40):
        sigma_mean = np.nanmean(sigma[k,:,:])
        append_field_to_b_file(fnb,u,k,'u-vel.',this_datetime,baclin,sigma_mean)
        append_field_to_a_file(fna,u,k)
        append_field_to_b_file(fnb,v,k,'v-vel.',this_datetime,baclin,sigma_mean)
        append_field_to_a_file(fna,v,k)
        append_field_to_b_file(fnb,dp,k,'thknss',this_datetime,baclin,sigma_mean)
        append_field_to_a_file(fna,dp,k)
        append_field_to_b_file(fnb,t,k,'temp',this_datetime,baclin,sigma_mean)
        append_field_to_a_file(fna,t,k)
        append_field_to_b_file(fnb,s,k,'salin',this_datetime,baclin,sigma_mean)
        append_field_to_a_file(fna,s,k)


    # plt.pcolormesh(dp[39,:,:].mask) ; plt.colorbar() ;  plt.show()
    # plt.pcolormesh(dp[39,:,:].filled()) ; plt.colorbar() ;  plt.show()
    #
    # plt.pcolormesh(t_layer_mean[39,:,:].mask) ; plt.colorbar() ;  plt.show()
    # plt.pcolormesh(t_layer_mean[39,:,:].filled()) ; plt.colorbar() ;  plt.show()


########################################################################
############### Derived thermodynamics functions #######################
########################################################################

def getT100(filename, missing=np.nan):
    """
    T100 is the average temperature within the top 100 m of the ocean.
    Where the bathymetry is shallower than 100 m,
    it is the average of the entire column.
    """
    ## Read
    t  = getField("temp", filename, missing)
    dz = getField("thknss", filename, missing) / 9806.0
    z_bottom, z_center, z_top = thickness2depths(dz)

    ## Calculate
    t_above_100m = t.copy()
    t_above_100m[t_above_100m==missing] = np.nan  # Set "missing" to NaN for the calculation.
    t_above_100m[z_bottom > 100.0] = np.nan
    t100 = np.nanmean(t_above_100m, axis=0)
    t100[np.isnan(t100)] = missing  # Set NaN back to "missing" if needed.

    ## Return
    return t100


def getDepthOfT(filename, threshold=26.0, missing=np.nan):
    """
    D26C is the depth in meters of the threshold (commonly 26C) isotherm.
    Commonly regarded as the thermocline depth in the tropics.
    It will be set to missing when the SST < threshold.
    It will be set to missing when the entire column never gets below the threshhold.
    """
    ## Read
    t  = getField("temp", filename, missing)
    dz = getField("thknss", filename, missing) / 9806.0
    z_bottom, z_center, z_top = thickness2depths(dz)

    S = t.shape
    ## Calculate
    d26 = missing + np.zeros((S[1],S[2]))
    for ii in range(S[2]):
        for jj in range(S[1]):

            if np.isnan(t[0,jj,ii]):
                d26[jj,ii] = missing
            elif t[0,jj,ii] == missing:
                d26[jj,ii] = missing
            elif t[0,jj,ii] < threshold:
                d26[jj,ii] = missing
            else:
                lt_thresh_idx0 = [x for x in range(len(t[:,jj,ii])) if t[x,jj,ii] < threshold]
                if len(lt_thresh_idx0) < 1:
                    d26[jj,ii] = missing
                else:
                    lt_thresh_idx = lt_thresh_idx0[0]
                    d26[jj,ii] = np.interp(threshold, t[lt_thresh_idx-1:lt_thresh_idx+1,jj,ii], z_center[lt_thresh_idx-1:lt_thresh_idx+1,jj,ii])

    ## Return
    return d26


########################################################################
############### Mixed Layer Depth Functions ############################
########################################################################

def getMixedLayerDepth(filename, delT=0.2, delS=0.03, ref_depth=10):
    """
    One definition of mixed layer depth is first level when the temperature
    or salinity difference is greater than a threshold, relative to a reference depth.
    This function first calculates the temperature and salinity based
    mixed layer depths (mldt and mlds, respectively),
    then returns the one that closer to the surface as
    "the" mixed layer depth (mld).
    By default, it will use the threshold of 0.2 C for temperature
    and 0.03 PSU for salinity.

    Returned values are a tuple of (mld,mldt,mlds)
    """
    import os.path

    dims2 = getDims(os.path.dirname(filename) + '/regional.grid.b')
    t = getField('temp', filename)
    s = getField('salin', filename)
    dz = getField('thknss', filename) / 9806.0
    z_bottom, z_center, z_top = thickness2depths(dz)

    mldt = np.nan*np.zeros(dims2)
    mlds = np.nan*np.zeros(dims2)
    mld = np.nan*np.zeros(dims2)

    for jj in range(dims2[0]):
        for ii in range(dims2[1]):
            if not np.isnan(t[0,jj,ii]):
                mldt[jj,ii] = mixedLayerDepthT(t[:,jj,ii],z_center[:,jj,ii],delT, ref_depth=10.0)
                mlds[jj,ii] = mixedLayerDepthS(s[:,jj,ii],z_center[:,jj,ii],delS, ref_depth=10.0)
                mld[jj,ii] = min(mldt[jj,ii],mlds[jj,ii])

    return (mld, mldt, mlds)


def mixedLayerDepthT(T,d,delT, ref_depth=10.0):
    """
    Computes mixed layer depth given a temperature and depth
    profiles and temperature difference criterion.
    Uses linear interpolation to find mixed layer depth between
    two discrete levels. If criterion is not satisfied,
    returns the last element of the depth list.

    Input arguments:
    T    :: list of vertical temperature profile
    d    :: list of depth values, of same length as T
    delT :: float; Temperature difference criterion in K
    """

    ref_temp = T[0]
    k_begin = 1

    if ref_depth > 0.1:
        ref_temp = np.interp(ref_depth, d, T)
        k_begin = int(np.ceil(np.interp(ref_depth, d, np.arange(len(d)))))

    Tm=ref_temp-delT
    for k in range(k_begin,len(T),1):
        if np.isfinite(T[k]):
            if T[k]<Tm:
                mld=(abs(T[k-1]-Tm)*d[k] \
                     +abs(Tm-T[k])*d[k-1])\
                     /(T[k-1]-T[k])
                return mld
        else:
            return d[k-1]
    return d[len(T)-1]


def mixedLayerDepthS(S,d,delS, ref_depth=10.0):
    """
    Computes mixed layer depth given a temperature and depth
    profiles and temperature difference criterion.
    Uses linear interpolation to find mixed layer depth between
    two discrete levels. If criterion is not satisfied,
    returns the last element of the depth list.

    Input arguments:
    S    :: list of vertical salinity profile
    d    :: list of depth values, of same length as T
    delS :: float; Salinity difference criterion in K
    """

    ref_sal = S[0]
    k_begin = 1

    if ref_depth > 0.1:
        ref_sal = np.interp(ref_depth, d, S)
        k_begin = int(np.ceil(np.interp(ref_depth, d, np.arange(len(d)))))

    Sm=ref_sal+delS
    for k in range(k_begin,len(S),1):
        if np.isfinite(S[k]):
            if S[k]>Sm:
                mld=(abs(S[k-1]-Sm)*d[k] \
                     +abs(Sm-S[k])*d[k-1])\
                     /(S[k]-S[k-1])
                return mld
        else:
            return d[k-1]
    return d[len(S)-1]


#
########################################################################
#
def str2(number):
    string=str(number)
    if len(string)<2:string='0'+string
    return string
#

#
########################################################################
##
## Main function.
## If this is called as a main function with a file provided as command line arg,
## then assume the intention is to do ab2nc on that file.

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print('Usage: python pyhycom.py filename.a')
        print('       To convert to filename.nc')
    else:
        filename = sys.argv[1]
        if os.path.exists(filename):
            ncfn = ab2nc(filename)
            print('Created '+ncfn)
        else:
            print('File does not exist: '+filename)
