"""
    @file:              applications.py
    @Author:            Maxence Larose

    @Creation Date:     10/2022
    @Last modification: 11/2022

    @Description:       This file contains the apply_transforms function which is used to apply transformations to
                        images and segmentations.
"""

from copy import deepcopy
from typing import Dict, Hashable, NamedTuple, Union

from monai.transforms import apply_transform as monai_apply_transform
from monai.transforms import Compose, EnsureChannelFirstD
from monai.transforms import MapTransform as MonaiMapTransform
import SimpleITK as sitk

from dicom2hdf.data_model import PatientDataModel
from dicom2hdf.transforms.transforms import Dicom2hdfTransform, Mode
from dicom2hdf.transforms.tools import convert_to_numpy, set_transforms_keys


class _SitkImageInfo(NamedTuple):
    spacing: tuple
    origin: tuple
    direction: tuple


def apply_transforms(
        patient_dataset: PatientDataModel,
        transforms: Union[Compose, Dicom2hdfTransform, MonaiMapTransform]
) -> None:
    """
    Applies transforms on images and segmentations.

    Parameters
    ----------
    patient_dataset : PatientDataModel
        A named tuple grouping the patient's data extracted from its DICOM files and the patient's medical image
        segmentation data extracted from the segmentation files.
    transforms : Union[Compose, Dicom2hdfTransform, MonaiMapTransform]
        A sequence of transformations to apply to images and segmentations. Dicom2hdfTransform are applied in the
        physical space, i.e on the SimpleITK image, while MonaiMapTransform are applied in the array space, i.e on
        the numpy array that represents the image. The keys for images are assumed to be the arbitrary series key
        set in 'series_descriptions'. For segmentation, keys are organ names. Note that if 'series_descriptions' is
        None, the keys for images are assumed to be modalities.
    """
    set_transforms_keys(patient_dataset=patient_dataset)

    if isinstance(transforms, Compose):
        for t in transforms.transforms:
            _apply_transform_on_segmentations(
                transform=t,
                patient_dataset=patient_dataset
            )
            _apply_transform_on_images(
                transform=t,
                patient_dataset=patient_dataset
            )
    else:
        _apply_transform_on_segmentations(
            transform=transforms,
            patient_dataset=patient_dataset
        )
        _apply_transform_on_images(
            transform=transforms,
            patient_dataset=patient_dataset
        )


def _apply_transform_on_images(
        patient_dataset: PatientDataModel,
        transform: Union[Dicom2hdfTransform, MonaiMapTransform]
) -> None:
    """
    Applies single transform on images.

    Parameters
    ----------
    patient_dataset : PatientDataModel
        A named tuple grouping the patient's data extracted from its DICOM files and the patient's medical image
        segmentation data extracted from the segmentation files.
    transform : Union[Dicom2hdfTransform, MonaiMapTransform]
        A transformation to apply on images. Dicom2hdfTransform are applied in the physical space, i.e on the
        SimpleITK image, while MonaiMapTransform are applied in the array space, i.e on the numpy array that represents
        the image. The keys for images are assumed to be the arbitrary series key set in 'series_descriptions'. For
        segmentation, keys are organ names. Note that if 'series_descriptions' is None, the keys for images are
        assumed to be modalities.
    """
    images = {data.image.transforms_key: data.image.simple_itk_image for data in patient_dataset.data}

    transformed_images_dict = _apply_transform(transform=transform, data=images, mode=Mode.IMAGE)
    for data in patient_dataset.data:
        image = data.image
        image.simple_itk_image = transformed_images_dict[image.transforms_key]


def _apply_transform_on_segmentations(
        patient_dataset: PatientDataModel,
        transform: Union[Dicom2hdfTransform, MonaiMapTransform]
) -> None:
    """
    Applies single transform on segmentations.

    Parameters
    ----------
    patient_dataset : PatientDataModel
        A named tuple grouping the patient's data extracted from its DICOM files and the patient's medical image
        segmentation data extracted from the segmentation files.
    transform : Union[Dicom2hdfTransform, MonaiMapTransform]
        A transformation to apply on segmentations. Dicom2hdfTransform are applied in the physical space, i.e on the
        SimpleITK image, while MonaiMapTransform are applied in the array space, i.e on the numpy array that represents
        the image. The keys for images are assumed to be the arbitrary series key set in 'series_descriptions'. For
        segmentation, keys are organ names. Note that if 'series_descriptions' is None, the keys for images are
        assumed to be modalities.
    """
    images = {data.image.transforms_key: data.image.simple_itk_image for data in patient_dataset.data}

    for image_and_segmentation_data in patient_dataset.data:
        segmentations = image_and_segmentation_data.segmentations

        if segmentations:
            for segmentation_data in segmentations:
                temp_dict = deepcopy(images)
                for organ_name, label_map in segmentation_data.simple_itk_label_maps.items():
                    temp_dict[organ_name] = label_map

                transformed_dict = _apply_transform(transform=transform, data=temp_dict, mode=Mode.SEGMENTATION)

                for img_key in images.keys():
                    transformed_dict.pop(img_key)

                segmentation_data.simple_itk_label_maps = transformed_dict


def _apply_transform(
        data: Dict[str, sitk.Image],
        transform: Union[Dicom2hdfTransform, MonaiMapTransform],
        mode: Mode
) -> Dict[Hashable, sitk.Image]:
    """
    Applies single transform on segmentations.

    Parameters
    ----------
    data : Dict[Hashable, sitk.Image]
        A dictionary of SimpleITK images to be transformed.
    transform : Union[Dicom2hdfTransform, MonaiMapTransform]
        A transformation to apply. Dicom2hdfTransform are applied in the physical space, i.e on the SimpleITK image,
        while MonaiMapTransform are applied in the array space, i.e on the numpy array that represents the image. The
        keys for images are assumed to be the arbitrary series key set in 'series_descriptions'. For segmentation,
        keys are organ names. Note that if 'series_descriptions' is None, the keys for images are assumed to be
        modalities.
    mode : Mode
        The mode.

    Returns
    -------
    transformed_data : Dict[Hashable, sitk.Image]
        A dictionary of transformed SimpleITK images.
    """
    if isinstance(transform, Dicom2hdfTransform):
        return _apply_dicom2hdf_transform(transform=transform, data=data, mode=mode)
    elif isinstance(transform, MonaiMapTransform):
        return _apply_monai_transforms(transform=transform, data=data)


def _apply_dicom2hdf_transform(
        data: Dict[str, sitk.Image],
        transform: Dicom2hdfTransform,
        mode: Mode
) -> Dict[Hashable, sitk.Image]:
    """
    Apply a Dicom2hdfTransform.

    Parameters
    ----------
    data : Dict[str, sitk.Image]
        A dictionary of SimpleITK images to be transformed.
    transform : Dicom2hdfTransform
        A transformation to apply to images and segmentations in the physical space, i.e on the SimpleITK image. Keys
        are assumed to be modality names for images and organ names for segmentations.
    mode : Mode
        Mode.

    Returns
    -------
    transformed_data : Dict[Hashable, sitk.Image]
        A dictionary of transformed SimpleITK images.
    """
    transform.mode = mode.value

    transformed_data = monai_apply_transform(transform=transform, data=data)
    transform.mode = Mode.NONE.value

    return transformed_data


def _apply_monai_transforms(
        data: Dict[str, sitk.Image],
        transform: MonaiMapTransform
) -> Dict[Hashable, sitk.Image]:
    """
    Apply a MonaiMapTransform.

    Parameters
    ----------
    data : Dict[str, sitk.Image]
        A dictionary of SimpleITK images to be transformed.
    transform : MonaiMapTransform
        A transformation to apply to images and segmentations in the array space, i.e on the numpy array that
        represents the image. Keys are assumed to be modality names for images and organ names for segmentations.

    Returns
    -------
    transformed_data : Dict[Hashable, sitk.Image]
        A dictionary of transformed SimpleITK images.
    """
    ensure_channel_first_d = EnsureChannelFirstD(keys=transform.keys, allow_missing_keys=True)
    transform = Compose([ensure_channel_first_d, transform])

    info = {}
    temp_dict = {}
    for k, img in data.items():
        info[k] = _SitkImageInfo(spacing=img.GetSpacing(), origin=img.GetOrigin(), direction=img.GetDirection())
        temp_dict[k] = sitk.GetArrayFromImage(data[k])

    transformed_data = monai_apply_transform(transform=transform, data=temp_dict)

    for k, img in transformed_data.items():
        transformed_img_array = convert_to_numpy(transformed_data[k])

        transformed_img_sitk = sitk.GetImageFromArray(transformed_img_array)
        transformed_img_sitk.SetSpacing(info[k].spacing)
        transformed_img_sitk.SetOrigin(info[k].origin)
        transformed_img_sitk.SetDirection(info[k].direction)

        transformed_data[k] = transformed_img_sitk

    return transformed_data
